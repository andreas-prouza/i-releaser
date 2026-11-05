import contextvars
import datetime
import copy
import hashlib
import json
import logging
import os

import threading

# from pydantic import validate_arguments

from etc import constants
from modules import action_type, current_user, deploy_action as da, errors, files, hooks, json_path, permissions, stage_status
from modules import deploy_object as do
from modules import stages as s
from modules import workflow as wf
from modules import deploy_version as dv
from modules.cmd_status import Status as Cmd_Status
from modules import meta_file_history as mfh
from modules.db import meta_file_history_data as mfhd, processing_user_data
from modules.db import deploy_object_data, processing_job_data, stage_data
from modules import processing_job
from modules.permission_config import check_user_permission
from modules import stage_status

from modules.meta_file_status import Meta_file_status


class StageNotReadyException(errors.Conflict_Error):
  pass


class StageNotRunnableException(errors.Conflict_Error):
  pass


# A stage in one of these status is running
STAGE_IN_PROCESS_STATUS = [stage_status.Status.IN_PROCESS, stage_status.Status.IN_PREPERATION, stage_status.Status.PREPARE]

# Only a stage in one of these status can be run
STAGE_RUNNABLE_STATUS = [stage_status.Status.READY, stage_status.Status.FAILED]

# A stage which has changed less than this time ago may still be running, so it can't be reset
STAGE_RESET_WAIT_SECONDS = 60

# Handler of the history log of the current run
_active_history: contextvars.ContextVar[logging.Handler|None] = contextvars.ContextVar('active_history', default=None)



class Meta_File:

    """
    Meta_File describes a information of a deployment
    It's the main controller
    """



    def __init__(self, project: str|None=None, workflow_name : str|None=None, workflow=None, 
                object_list: str|None=None, create_time=None, update_time=None, status :Meta_file_status|None=None, 
                deploy_version : int|None=None, deploy_version_id : int|None=None, stages: s.Stage_List_list|None=None,
                processing_users: list|None=None, custom_data: dict|None=None,
                id: int|None=None, meta_dir: str|None=None, parallel_deployment_execution_allowed: bool=False):

      #logging.debug(f"{sys.path=}")

      self.id: int|None = id
      self.stages: s.Stage_List_list = stages or s.Stage_List_list()
      self.current_running_stage = None
      self.status: Meta_file_status = status or Meta_file_status.NEW

      self.backup_deploy_lib = None
      self.main_deploy_lib = None
      self.remote_deploy_lib = None
      self.commit = None
      self.release_branch = None
      self.project: str|None = project
      self.deploy_version: int|None = deploy_version
      self.deploy_version_id: int|None = deploy_version_id
      self.object_list: str|None = object_list
      self.run_history: mfh.Meta_File_History_List_list = mfh.Meta_File_History_List_list()
      self._history_handler: logging.Handler|None = None
      self._history_token: contextvars.Token|None = None
      # Parallel steps share this object. Two saves at the same time could add a new sub-step twice.
      self._save_lock = threading.Lock()
      self.processing_users: list = processing_users or []
      # Queued and running jobs of the processing service
      self.processing_jobs: list[processing_job.Processing_Job] = []
      self.custom_data: dict|None = custom_data or {}
        
      self.update_time: datetime.datetime = update_time or datetime.datetime.now()
      self.create_time: datetime.datetime = create_time or datetime.datetime.now()
      self.parallel_deployment_execution_allowed: bool = parallel_deployment_execution_allowed or False
      # Values in the database, see app_sqlite.update_changes
      self.saved_values: dict|None = None

      if isinstance(self.update_time, str):
        self.update_time = datetime.datetime.fromisoformat(self.update_time)

      if isinstance(self.create_time, str):
        self.create_time = datetime.datetime.fromisoformat(self.create_time)

      if self.create_time == None:
        self.create_time = datetime.datetime.now()
        self.update_time = self.create_time

      self.meta_dir: str|None = meta_dir
      if self.meta_dir is None:
        self.meta_dir = constants.C_META_DIR.format(project=project, create_date=str(self.create_time.date()), deploy_version=deploy_version)

      if os.path.exists(self.meta_dir) is False:
        os.makedirs(self.meta_dir, exist_ok=True)
        
      self.workflow = wf.Workflow(name=workflow_name, dict=workflow)
      #logging.debug(f"Meta Workflow: {self.workflow.get_dict()}")
      
      if self.project is None:
        self.project = self.workflow.default_project
          
      self.deploy_objects = do.Deploy_Object_List()

      self.release_branch = constants.C_GIT_BRANCH_RELEASE.replace('{deploy_version}', str(self.deploy_version)).replace('{project}', self.project)

      if self.id is not None:
        self.set_libs()



    def activate_history(self) -> bool:
      """Writes all log records of the current context into a new history log of this deployment,
      until deactivate_history() is called. Parallel steps run in a copy of this context, so they are included.

      Returns:
          bool: False if the history was already active
      """
      if self._history_handler is not None:
        return False

      history: mfh.Meta_File_History = mfhd.create_new_meta_file_history(meta_file_id=self.id)
      self.run_history.append(history)

      hdl = logging.FileHandler(history.log.removeprefix('file://'), encoding='utf-8')
      if logging.root.handlers:
        hdl.setFormatter(logging.root.handlers[0].formatter)
      # Other threads (e.g. web requests or other deployments) must not end up in this history
      hdl.addFilter(lambda record: _active_history.get() is hdl)
      logging.getLogger().addHandler(hdl)

      self._history_handler = hdl
      self._history_token = _active_history.set(hdl)
      return True



    def deactivate_history(self) -> None:

      if self._history_handler is None:
        return

      logging.getLogger().removeHandler(self._history_handler)
      self._history_handler.close()
      self._history_handler = None
      _active_history.reset(self._history_token)



    def save(self, update_meta_file=True):
        """Saves the current state of the meta file to the database."""
        if not update_meta_file:
          logging.warning("Update meta file is set to False. Meta file will not be saved")
          return
            
        from modules.db import meta_file_data

        with self._save_lock:
          self.update_time = datetime.datetime.now()
          meta_file_data.save_meta_file(self)


    def set_status(self, status, update_meta_file=True):

      logging.debug(f"Set status to {status}")

      if type(status) == str:
        status = Meta_file_status(status)

      logging.debug(f"Update meta file: {update_meta_file}")

      if self.status == Meta_file_status.CANCELED:
        raise errors.Conflict_Error("Deployment has been canceled already. It's not possible to change the status!")

      old_status = self.status

      if update_meta_file and status is not Meta_file_status.NEW:
        logging.debug(f"Update meta file: Finished 1.0")
        dv.Deploy_Version.update_deploy_status(self.project, self.deploy_version, status, self.commit, parallel_deployment_execution_allowed=self.parallel_deployment_execution_allowed)
        logging.debug(f"Update meta file: Finished 1")
        self.status = status
        self.save()

      self.status = status
      logging.debug(f"Finished meta file status set to {self.status.value}")

      if update_meta_file and status != old_status:
        if status == Meta_file_status.FINISHED:
          hooks.emit(hooks.Event.DEPLOYMENT_FINISHED, self)
        elif status == Meta_file_status.CANCELED:
          hooks.emit(hooks.Event.DEPLOYMENT_CANCELED, self)




    #@check_user_permission(permissions.PermissionAction.CHANGE_CHECK_ERROR)
    def set_action_check(self, stage_id: int, action_id: int, check: bool, current_user: str) -> None:
      stage = self.get_stage_by_id(stage_id)

      if stage is None:
        raise errors.Not_Found_Error(f"Stage id {stage_id} not found")

      if stage.status == stage_status.Status.FINISHED:
        raise errors.Conflict_Error(f"Stage {stage.name} is already finished")

      check_user_permission(permissions.PermissionAction.CHANGE_CHECK_ERROR, workflow=self.workflow.name, stage=stage.name)
      stage.actions.set_action_check(action_id, check)

      processing_user_data.create_action_log(action_type.Action_type.SET_CHECK_ERROR, details=f"Set check error to {check} for action id {action_id}", meta_file=self, stage=stage)
      self.save()



    #@check_user_permission(permissions.PermissionAction.RUN_WORKFLOW)
    def set_next_stage(self, from_stage: s.Stage):
      """Add next stages to open_stages list

      Args:
          from_stage (s.Stage): Current finished stage
      """
      logging.debug(f"Set next stage from '{from_stage.name}' (ID: {from_stage.id})")
      next_stages = from_stage.next_stages

      logging.debug(f"Next stages: {next_stages=}")

      for next_stage in next_stages:

        existing_stages = [*self.stages.get_stages_by_name(next_stage)]


        logging.debug(f'{next_stage=}')
        # Check if already processed
        if len(existing_stages) > 0:
          for es in existing_stages:
            logging.debug(f"Stage ({next_stage}) already processed: {es.id}")
            # Parallel branches lead to the same stage: only the first one activates it
            stage_data.activate_stage(es.id)
            from_stage.next_stage_ids.append(es.id)
            es.from_stage_id.append(from_stage.id)
          continue

        logging.debug(f"Register new stage for {next_stage}")
        next_stage_object = s.Stage.get_stage_from_workflow(self.workflow, next_stage)
        logging.debug(f"New stage id {next_stage_object.id}")
        
        from_stage.next_stage_ids.append(next_stage_object.id)
        next_stage_object.from_stage_id.append(from_stage.id)
        self.stages.append(next_stage_object)
        self.copy_object_actions_2_open_stages(next_stage_object.id)
      
      self.save()
      self.refresh_state()

      logging.debug(f'{self.stages.summary()=}')



    def refresh_state(self) -> None:
      """
      Takes over the status of this deployment and its stages from the database.
      Another stage which runs at the same time, or a user, may have changed them since they have been loaded.
      Unsaved changes of the status are lost, so save them first.
      """

      if self.id is None:
        return

      from modules.db import meta_file_data

      status = meta_file_data.get_status(self.id)
      if status is not None:
        self.status = status

      stage_data.refresh_stages(self.stages, self.id)



    def get_open_stages(self) -> s.Stage_List_list:
      open_stages = s.Stage_List_list()
      for stage in self.stages:
        if stage.status not in [stage_status.Status.FINISHED]:
          open_stages.append(stage)
      return open_stages


    def get_processed_stages(self) -> s.Stage_List_list:
      processed_stages = s.Stage_List_list()
      for stage in self.stages:
        if stage.status in [stage_status.Status.FINISHED]:
          processed_stages.append(stage)
      return processed_stages



    def get_next_stages(self, from_stage: s.Stage) -> s.Stage_List_list:
      """Get's following stages objects from a stage
          This is used for workflow drawing in flowchart.py

      Args:
          from_stage (s.Stage): Basis stage object

      Returns:
          s.Stage_List_list: List of stages
      """

      next_stages = s.Stage_List_list()

      # if already processed, get from self.stages
      for next_id in from_stage.next_stage_ids:
        if next_id in next_stages.get_all_ids():
          continue
        ns = self.get_stage_by_id(next_id)
        next_stages.append(ns)

      logging.debug(f"Next stages for {from_stage.name} ({from_stage.id}): {next_stages.get_all_ids()}")
      if len(next_stages) > 0:
        return next_stages

      logging.debug(f"Next stages 2 for {from_stage.name}: {from_stage}")

      for ns in from_stage.next_stages:
        next_stages_list = self.get_stages_by_name(stage=ns)

        if len(next_stages_list) == 0:
          logging.warning(f"Next stages 3 for {from_stage.name}: {ns} not found in open stages")
          continue

        next_stages.append(next_stages_list[0])

      return next_stages




    def get_last_finished_stage(self) -> s.Stage|None:
      """The stage which has been finished last (None if no stage has been finished yet)"""

      finished_stages = self.get_processed_stages()
      if len(finished_stages) == 0:
        return None

      # update_time is set when the stage gets finished
      return max(finished_stages, key=lambda stage: (stage.update_time, stage.id))



    def check_reset_last_finished_stage(self) -> s.Stage:
      """Returns the stage which has been finished last, if its status can be reset

      Raises:
          Exception: If the deployment has been finished or canceled, a stage is in process
              or no stage has been finished yet
      """

      if self.status in [Meta_file_status.FINISHED, Meta_file_status.CANCELED]:
        raise errors.Conflict_Error(f"Deployment is already {self.status.value}. The status of its stages can't be reset anymore!")

      stages_in_process = [stage.name for stage in self.stages if stage.status in STAGE_IN_PROCESS_STATUS]
      if len(stages_in_process) > 0:
        raise errors.Conflict_Error(f"Stage(s) {stages_in_process} still in process. The last finished stage can't be reset now!")

      if self.status == Meta_file_status.IN_PROCESS:
        raise errors.Conflict_Error(f"Deployment is in status '{self.status.value}'. The last finished stage can't be reset now!")

      for job in processing_job_data.get_active_jobs(self.id):
        stage = self.get_stage_by_id(job.stage_id)
        raise errors.Conflict_Error(f"Stage '{stage.name if stage else job.stage_id}' is {job.status.value} in the processing service (job {job.id}). The last finished stage can't be reset now!")

      last_finished_stage = self.get_last_finished_stage()
      if last_finished_stage is None:
        raise errors.Conflict_Error("No stage has been finished yet!")

      return last_finished_stage



    #@check_user_permission(permissions.PermissionAction.RUN_WORKFLOW)
    def reset_last_finished_stage(self, stage_id: int) -> s.Stage:
      """Sets the stage which has been finished last back to 'ready', so it can be run again.
      Its next stages are set back to 'new', unless another finished stage leads to them as well.
      The status of its steps stays, so they will only be run again with continue_run=False.

      Args:
          stage_id (int): Needs to be the stage which has been finished last

      Returns:
          s.Stage: The reset stage
      """

      stage = self.check_reset_last_finished_stage()

      if stage.id != int(stage_id):
        raise errors.Conflict_Error(f"Stage id {stage_id} is not the last finished stage. The last finished stage is '{stage.name}' ({stage.id})!")

      other_finished_stages = [fs for fs in self.get_processed_stages() if fs.id != stage.id]

      for next_stage_id in set(stage.next_stage_ids):

        if any(next_stage_id in fs.next_stage_ids for fs in other_finished_stages):
          continue

        next_stage = self.stages.get_stage(next_stage_id)
        if next_stage.status in [stage_status.Status.READY, stage_status.Status.FAILED]:
          logging.info(f"Set next stage {next_stage.name} ({next_stage.id}) back to '{stage_status.Status.NEW.value}'")
          next_stage.status = stage_status.Status.NEW
          next_stage.update_time = datetime.datetime.now()

      # They will be set again, when the stage gets finished
      stage.next_stage_ids = []
      stage.status = stage_status.Status.READY
      stage.update_time = datetime.datetime.now()
      logging.info(f"Reset finished stage {stage.name} ({stage.id}) to '{stage.status.value}'")

      # Saves the stages as well
      self.set_status(Meta_file_status.READY)

      return stage



    def check_stage_reset(self, stage: s.Stage) -> None:
      """
      Raises:
          errors.Conflict_Error: If the stage is not hanging, but may still be running
      """

      if stage.status not in STAGE_IN_PROCESS_STATUS:
        raise errors.Conflict_Error(f"Stage {stage.name} is in status '{stage.status.value}'. Only a stage which is in process can be reset!")

      for job in processing_job_data.get_active_jobs(self.id):
        if job.stage_id == stage.id:
          raise errors.Conflict_Error(f"Stage {stage.name} is {job.status.value} in the processing service (job {job.id}). It can't be reset!")

      seconds = (datetime.datetime.now() - stage.update_time).total_seconds()

      if seconds < STAGE_RESET_WAIT_SECONDS:
        raise errors.Conflict_Error(f"Stage {stage.name} has changed {int(seconds)} seconds ago and may still be running. It can be reset after {STAGE_RESET_WAIT_SECONDS} seconds!")



    def reset_stage(self, stage: s.Stage) -> None:
      """Sets a stage which hangs in process back to 'ready', e.g. after the web app has been restarted"""

      self.check_stage_reset(stage)
      stage.set_status(stage_status.Status.READY)
      self.set_status_after_stage_run()



    def reset_status(self) -> None:
      """Corrects a deployment which hangs in process: its hanging stages are set back and its status follows from its stages"""

      if self.status in [Meta_file_status.FINISHED, Meta_file_status.CANCELED]:
        raise errors.Conflict_Error(f"Deployment is already {self.status.value}!")

      stages = [stage for stage in self.get_open_stages() if stage.status in STAGE_IN_PROCESS_STATUS]

      for stage in stages:
        self.check_stage_reset(stage)

      for stage in stages:
        stage.set_status(stage_status.Status.READY)

      self.set_status_after_stage_run()
      self.check_deployment_finish()



    def get_stages_needs_2_get_finished(self, stage: s.Stage) -> list[str]:
      if stage.after_stages_finished is None or len(stage.after_stages_finished) == 0:
        return []

      waiting_for_stages = []

      for stage_name in stage.after_stages_finished:
        if stage_name not in self.get_processed_stages().get_all_names():
          waiting_for_stages.append(stage_name)
      
      return waiting_for_stages



    #@check_user_permission(permissions.PermissionAction.RUN_WORKFLOW)
    def run_current_stages(self) -> None:

      for open_stage_id in self.get_open_stages().get_all_ids():
        self.run_current_stage(open_stage_id)



    #@check_user_permission(permissions.PermissionAction.RUN_WORKFLOW)
    def run_current_stage_as_thread(self, stage_id: int, processing_step: str|None=None, continue_run=True) -> threading.Thread:

      logging.debug(f"Start deployment check")
      self.check_deployment_ready_2_run(stage_id=stage_id, processing_step=processing_step)
      logging.debug(f"Deployment check successfully passed")

      # Here and not in the thread, so a second start fails with an error for the user
      self.claim_stage(stage_id)

      # The thread needs the user of this request
      t = threading.Thread(target=contextvars.copy_context().run, args=(self.run_current_stage, stage_id, processing_step, continue_run, True))
      t.start()
      return t



    def claim_stage(self, stage_id: int) -> None:
      """
      Sets the stage to `in process`, as last check before it's run. It succeeds only once, even with multiple processes.

      Raises:
          StageNotRunnableException: If the stage can't be run (anymore)
      """

      if not stage_data.claim_stage(stage_id, exclusive=not self.parallel_deployment_execution_allowed):
        raise StageNotRunnableException(f"Stage id {stage_id} can't be run: it's not ready or another stage of this deployment is in process")

      stage_data.refresh_stages(self.stages, self.id)



    def check_no_active_job(self, stage_id: int) -> None:
      """A stage which is queued or processed by the processing service can't be started again"""

      for job in processing_job_data.get_active_jobs(self.id):

        if job.stage_id == stage_id or not self.parallel_deployment_execution_allowed:
          stage = self.get_stage_by_id(job.stage_id)
          raise errors.Conflict_Error(f"Stage '{stage.name if stage else job.stage_id}' is already {job.status.value} in the processing service (job {job.id})!")



    #@check_user_permission(permissions.PermissionAction.RUN_WORKFLOW)
    def run_current_stage_as_job(self, stage_id: int, processing_step: str|None=None, continue_run=True) -> processing_job.Processing_Job:
      """Adds the run of the given stage to the queue of the processing service.
      It's run there in the name of the current user.
      """

      self.check_no_active_job(stage_id)

      logging.debug(f"Start deployment check")
      self.check_deployment_ready_2_run(stage_id=stage_id, processing_step=processing_step)
      logging.debug(f"Deployment check successfully passed")

      return processing_job_data.create_job(meta_file_id=self.id, stage_id=stage_id, processing_step=processing_step, continue_run=continue_run, user=current_user.get_user(),
                                            exclusive=not self.parallel_deployment_execution_allowed)



    #@check_user_permission(permissions.PermissionAction.RUN_WORKFLOW)
    def start_stage(self, stage_id: int, processing_step: str|None=None, continue_run=True) -> dict:
      """Runs the given stage in the background.
      Depending on the processing mode (see processing_settings) by the processing service or in a thread of the current process.

      Returns:
          dict: `mode` and for the processing service also `job_id` and `service_running`
      """

      # Read for each start: the mode can be changed in the web app
      from modules import processing_settings

      if processing_settings.get_processing_mode() == 'thread':
        # Stages which have been queued before the mode was changed
        self.check_no_active_job(stage_id)
        self.run_current_stage_as_thread(stage_id, processing_step, continue_run)
        return {'mode': 'thread'}

      # Imported here, as it imports this module
      from modules import processing_service

      job = self.run_current_stage_as_job(stage_id, processing_step, continue_run)

      service_running = processing_service.notify()
      if not service_running:
        logging.warning(f"Processing service is not running. Job {job.id} stays in the queue until it's started.")

      return {'mode': 'service', 'job_id': job.id, 'service_running': service_running}



    def check_deployment_ready_2_run(self, stage_id: int, processing_step: str|None=None):
      """
      Raises:
          errors.Not_Found_Error: If the stage doesn't exist
          StageNotRunnableException: If the stage or the deployment isn't in a status to run
          StageNotReadyException: If the stage waits for other stages
      """

      self.refresh_state()

      runable_stage = self.get_stage_by_id(stage_id)

      if runable_stage is None:
        raise errors.Not_Found_Error(f"Stage id '{stage_id}' not found in this deployment")

      if self.status in [Meta_file_status.FINISHED, Meta_file_status.CANCELED]:
        raise StageNotRunnableException(f"Deployment is already {self.status.value}!")

      if runable_stage.status not in STAGE_RUNNABLE_STATUS:
        raise StageNotRunnableException(f"Stage {runable_stage.name} ({stage_id}) is in status '{runable_stage.status.value}'. It can't be run!")

      if not self.parallel_deployment_execution_allowed:

        stages_in_process = [stage.name for stage in self.stages if stage.status in STAGE_IN_PROCESS_STATUS]
        if len(stages_in_process) > 0:
          raise StageNotRunnableException(f"Stage(s) {stages_in_process} still in process. Stage {runable_stage.name} can't be run at the same time!")

        if self.status not in [Meta_file_status.READY, Meta_file_status.FAILED]:
          raise StageNotRunnableException(f"Meta file is not in status 'ready', but in status '{self.status.value}'!")
  
      if processing_step is not None and processing_step not in runable_stage.processing_steps:
        raise errors.Invalid_Input_Error(f"Processing step '{processing_step}' is not defined in stage '{runable_stage.name}' (id {runable_stage.id}). Defined steps are: {runable_stage.processing_steps}")

      waiting_for_stages = self.get_stages_needs_2_get_finished(runable_stage)
      if len(waiting_for_stages) > 0:
        e = StageNotReadyException(f"Stage {runable_stage.name} ({stage_id}) is still waiting for other stages to get finished: {waiting_for_stages}")
        logging.exception(e, stack_info=True)
        raise e

      dv.Deploy_Version.validate_deployment(self.project, self.deploy_version, Meta_file_status.IN_PROCESS, parallel_deployment_execution_allowed=self.parallel_deployment_execution_allowed)




    #@check_user_permission(permissions.PermissionAction.RUN_WORKFLOW)
    def run_current_stage(self, stage_id: int, processing_step: str|None=None, continue_run=True, claimed=False) -> None:
      """Run given stage

      Args:
          stage_id (int): Stage id
          processing_step (str, optional): Step of stage. Defaults to None.
              If None, all steps will be issued
          continue_run (bool, optional):
              True: Continiue from first step which has not been finished
              False: Run all steps from this stage, even if they already have been finished successful
          claimed (bool, optional): The stage has already been checked and set to `in process` (see claim_stage)

      Raises:
          Exception: If a processing step was given, which is not in the step list of that stage
      """
      # False if already active, e.g. for stages which are run immediately after the previous one
      activated = self.activate_history()

      try:
        self._run_current_stage(stage_id, processing_step, continue_run, claimed)
      finally:
        if activated:
          self.deactivate_history()



    def _run_current_stage(self, stage_id: int, processing_step: str|None=None, continue_run=True, claimed=False) -> None:

      logging.debug(f"Run current stage with id {stage_id} and processing step {processing_step}")

      if not claimed:
        self.check_deployment_ready_2_run(stage_id=stage_id, processing_step=processing_step)
        logging.debug('Check passed')
        self.claim_stage(stage_id)

      runable_stage = self.stages.get_stage(id=stage_id)
      logging.debug(f"Runable stage: {runable_stage.name} ({runable_stage.id}) with processing step {processing_step} in status {runable_stage.status}")

      try:
        logging.debug("Set meta file status to 'in process'")
        self.set_status(Meta_file_status.IN_PROCESS)
      except Exception as err:
        logging.exception(err, stack_info=True)
        # It has not been started
        runable_stage.set_status(stage_status.Status.READY)
        raise err

      from modules.ibm_i_commands import IBM_i_commands
      logging.debug(f"Create IBM i commands instance")
      cmd = IBM_i_commands(self)
      
      logging.info(f"Run stage {runable_stage.name} (id {runable_stage.id}), {processing_step=}")

      self.current_running_stage = runable_stage

      try:
        cmd.run_commands(stage=runable_stage, processing_step=processing_step, continue_run=continue_run)
      except Exception as err:
        logging.exception(err, stack_info=True)

        if runable_stage.status != stage_status.Status.FAILED:
          runable_stage.set_status(stage_status.Status.FAILED)

        self.save()
        self.set_status_after_stage_run()
        hooks.emit(hooks.Event.STAGE_FAILED, self, runable_stage)
        raise err

      logging.info(f"All actions completed '{runable_stage.name}'")

      self.save()
      self.check_stage_finish(runable_stage)

      self.check_deployment_finish()
      logging.info(f"Finished run of stage '{runable_stage.name}'")



    def set_status_after_stage_run(self) -> None:
      """Sets the status of the deployment which follows from the current status of its stages. Other stages may still be in process."""

      self.refresh_state()

      if self.status == Meta_file_status.CANCELED:
        logging.info("Deployment has been canceled while the stage was running")
        return

      if any(stage.status in STAGE_IN_PROCESS_STATUS for stage in self.stages):
        return

      if any(stage.status == stage_status.Status.FAILED for stage in self.stages):
        self.set_status(Meta_file_status.FAILED)
        return

      self.set_status(Meta_file_status.READY)



    def check_stage_finish(self, stage: s.Stage) -> None:

      logging.debug("Check if stage has been finished")
      
      for action in stage.actions:

        if action.status not in [Cmd_Status.FINISHED, Cmd_Status.FAILED] or (action.status == Cmd_Status.FAILED and action.check_error == True):

          logging.info(f"Action {action.id} is in status '{action.status}'. So stage is not finished yet")
          # if stage is not completed, don't set the FINISHED status.
          if stage.status in STAGE_IN_PROCESS_STATUS:
            stage.set_status(stage_status.Status.READY)

          self.set_status_after_stage_run()
          return

      # Needed to find the last finished stage
      stage.set_status(stage_status.Status.FINISHED)

      # Must be READY before the next stages, as they may be run immediately
      self.set_status_after_stage_run()

      # Before set_next_stage, as it may finish the whole deployment
      hooks.emit(hooks.Event.STAGE_FINISHED, self, stage)

      if self.status == Meta_file_status.CANCELED:
        return

      logging.info(f"Stage {stage.name} ({stage.id}) has been finished. Setting next stage(s) {stage.next_stages}")
      self.set_next_stage(stage)

      # Only the next stages of the finished stage, as stages which are not reached yet are open too
      for next_stage in self.get_open_stages():

        if next_stage.name not in stage.next_stages or next_stage.status != stage_status.Status.READY:
          continue

        without_steps = len(next_stage.processing_steps) == 0

        if not next_stage.run_immediate and not without_steps:
          continue

        try:
          self.run_current_stage(next_stage.id)
        except (StageNotReadyException, StageNotRunnableException) as e:
          # It waits for other stages, or a parallel branch has been faster
          logging.info(f"Stage {next_stage.name} is not run now: {e}")
          continue

        if without_steps:
          processing_user_data.create_action_log(action_type.Action_type.RUN_STAGE, details="Finished automatically: stage without steps", meta_file=self, stage=next_stage)



    def check_deployment_finish(self) -> None:

      self.refresh_state()

      if len(self.get_open_stages()) > 0 or self.status == Meta_file_status.FINISHED:
        return

      from modules.db import meta_file_data

      # Parallel stages may finish at the same time, but the deployment is only finished once
      if self.status == Meta_file_status.CANCELED or not meta_file_data.claim_finished(self.id):
        self.refresh_state()
        return

      logging.info(f"Deployment of project {self.project} version {self.deploy_version} has been finished.")
      self.set_status(Meta_file_status.FINISHED)



    def set_libs(self):
      self.main_deploy_lib = f"d{str(self.id).zfill(9)}"
      self.backup_deploy_lib = f"b{str(self.id).zfill(9)}"
      self.remote_deploy_lib = f"r{str(self.id).zfill(9)}"



    
    def add_deploy_object(self, object: do.Deploy_Object):

      if object.id is not None:
        self.deploy_objects.add_object(object)
        return
      
      new_obj: do.Deploy_Object = deploy_object_data.create_deploy_object(meta_file_id=self.id, object=object)
      self.deploy_objects.add_object(new_obj)





    
    def set_deploy_objects(self, objects: do.Deploy_Object_List):

      for obj in objects:
        self.add_deploy_object(obj)



    def get_stage_by_id(self, stage_id: int) -> s.Stage|None:

      if type(stage_id) == str:
        stage_id = int(stage_id)

      if self.get_open_stages() is not None and stage_id in self.get_open_stages().get_all_ids():
        return self.get_open_stages().get_stage(stage_id)

      if self.get_processed_stages() is not None and stage_id in self.get_processed_stages().get_all_ids():
        return self.get_processed_stages().get_stage(stage_id)
      
      logging.error(f'No stage found with id {stage_id}. Existing: {self.get_open_stages().get_all_ids()=}, {self.get_processed_stages().get_all_ids()=}')



    def get_stages_by_name(self, stage: str) -> s.Stage_List_list:

      if self.get_open_stages() is not None and stage in self.get_open_stages().get_all_names():
        return self.get_open_stages().get_stages_by_name(stage)

      if self.get_processed_stages() is not None and stage in self.get_processed_stages().get_all_names():
        return self.get_processed_stages().get_stages_by_name(stage)

      return s.Stage_List_list()


    
    def get_actions(self, processing_step: str|None=None, stage_id: int|None=None, action_id: int|None=None, include_subactions: bool=True) -> list[da.Deploy_Action]:

      action_list: list[da.Deploy_Action]=[]

      if stage_id is None:
        raise Exception(f"Stage id is None")

      stage_obj = self.get_stage_by_id(stage_id)

      action_list=stage_obj.actions.get_actions(processing_step=processing_step, action_id=action_id, include_subactions=include_subactions)
      
      action_list = action_list + self.deploy_objects.get_actions(processing_step=processing_step, stage=stage_obj.name, action_id=action_id, include_subactions=include_subactions)
      
      return action_list








    #@check_user_permission(permissions.PermissionAction.CANCEL_WORKFLOW)
    def cancel_deployment(self):
      self.set_status(Meta_file_status.CANCELED)
      logging.info('Deployment has been canceled!')
      self.save()



    def get_editable_custom_fields(self) -> list[dict]:
      """Returns the editable fields of the workflow together with their current value (None if not set yet)."""

      fields = []
      for path in self.workflow.editable_fields:
        value = json_path.get_value(self.custom_data, path)
        fields.append({'path': path, 'exists': value is not json_path.MISSING, 'value': None if value is json_path.MISSING else value})
      return fields



    def update_custom_data(self, fields: dict) -> list[str]:
      """
      Sets the given fields ({JSONPath: value}) in the custom data.
      Only fields which are listed in `editable_fields` of the workflow are allowed.

      Returns:
          List of the changed paths
      """

      allowed = {json_path.normalize(p): p for p in self.workflow.editable_fields}
      changes = {}

      for path, value in fields.items():
        normalized = json_path.normalize(path)
        if normalized not in allowed:
          raise errors.Invalid_Input_Error(f"Field '{path}' is not editable in workflow '{self.workflow.name}'!")
        changes[allowed[normalized]] = value

      def change(custom_data: dict) -> dict:
        # Work on a copy, so a failing path does not leave partially changed data
        new_data = copy.deepcopy(custom_data)
        for path, value in changes.items():
          json_path.set_value(new_data, path, value)

        if len(json.dumps(new_data)) > constants.C_MAX_CUSTOM_DATA_SIZE:
          raise errors.Invalid_Input_Error(f"Custom data is larger than {constants.C_MAX_CUSTOM_DATA_SIZE} bytes")

        return new_data

      from modules.db import meta_file_data

      self.custom_data = meta_file_data.change_custom_data(self.id, change)
      self.saved_values = None
      self.save()
      hooks.emit(hooks.Event.CUSTOM_DATA_CHANGED, self)
      return list(changes.keys())



    # Load meta file based on its version number
    @staticmethod
    #@check_user_permission(permissions.PermissionAction.READ)
    def load_version(project:str, version: int) -> 'Meta_File':

      from modules.db import meta_file_data
      return meta_file_data.get_meta_file(project, version)



    def get_all_data_as_dict(self) -> dict:

      dict = {}
      dict['general'] = {'workflow':        self.workflow.get_dict(),
                         'id':              self.id,
                         'project':         self.project,
                         'deploy_version':  self.deploy_version,
                         'commit':          self.commit,
                         'release_branch':  self.release_branch,
                         'create_time':     self.create_time,
                         'update_time':     self.update_time,
                         'meta_dir':        self.meta_dir,
                         'status':          self.status.value,
                         'object_list':     self.object_list,
                         'processed_stages':  self.get_processed_stages().get_dict(),
                         'open_stages':  self.get_open_stages().get_dict(),
                         'parallel_deployment_execution_allowed':  self.parallel_deployment_execution_allowed,
                        }
      dict['deploy_libs'] = {'main_lib':    self.main_deploy_lib,
                             'remote_lib':  self.remote_deploy_lib,
                             'backup_lib':  self.backup_deploy_lib,
                            }
      #dict['deploy_cmds'] = self.get_actions_as_dict()
      dict['processing_users'] = self.processing_users
      dict['processing_jobs'] = [job.get_dict() for job in self.processing_jobs]
      dict['objects'] = self.deploy_objects.get_objects_as_list_of_dict()
      dict['run_history'] = self.run_history.get_list()
      dict['custom_data'] = self.custom_data
      logging.debug(f"Number of histories: {len(self.run_history)}")

      return dict



    @staticmethod
    def _state_hash(data) -> str:
      return hashlib.md5(json.dumps(data, sort_keys=True, default=str).encode(), usedforsecurity=False).hexdigest()[:12]



    @staticmethod
    def _get_action_state(actions: list[dict]) -> list:
      """Reduces action dicts (including sub actions) to the properties which change while a stage is running."""

      return [[a['id'],
               a['status'],
               a['check_error'],
               [[h['id'], h['status']] for h in a['run_history']],
               Meta_File._get_action_state(a['sub_actions'])
              ] for a in actions]



    def get_state_signature(self) -> dict:
      """Returns hashes of the current state, used by the web app to detect changes (auto refresh).

      * ``page``: state of the deployment, its stages, its deployed objects, the deployment history
        and its jobs of the processing service
      * ``stages``: state of each stage including its processing steps (actions), by stage id
      """

      page_state = {
        'status': self.status.value,
        'stages': [[stage.id, stage.status.value] for stage in self.stages],
        'jobs': [[job.id, job.status.value] for job in self.processing_jobs],
        'objects': [[obj['id'], obj['deploy_status']] for obj in self.deploy_objects.get_objects_as_list_of_dict()],
        'run_history': [h['id'] for h in self.run_history.get_list()],
      }

      stage_states = {}
      for stage in self.stages:
        stage_states[stage.id] = Meta_File._state_hash([stage.status.value, Meta_File._get_action_state(stage.actions.get_actions_as_dict())])

      return {'page': Meta_File._state_hash(page_state), 'stages': stage_states}



    def import_objects_from_config_file(self):
      """
      1. Import object list
         Objects to be deployed
      
      2. Import object specific actions
         These actions will be added in set_next_stage function
      """
      '''
      {level} | {lib on production system} | {lib on source system} | {object to be saved}
      1|prouzalib|prouzadev|testlog_test|prouzalib/qrpglesrc/testlog_test.rpgle.pgm
      '''

      if self.object_list is None:# and not os.path.exists(constants.C_OBJECT_LIST):
        e = Exception(f"No object list defined. No objects will be imported. {self.object_list=}")
        logging.exception(e, stack_info=True)
        raise e
      
      logging.debug(f"Abs. file: {os.path.abspath(self.object_list)}")

      if not os.path.exists(self.object_list):
        raise Exception(f"Object list {self.object_list} does not exist")

      logging.debug(f"File: {self.object_list}")

      # Imported again (e.g. the stage is run again): the objects would exist twice
      deploy_object_data.delete_deploy_objects(self.id)
      self.deploy_objects = do.Deploy_Object_List()

      file = files.readFile(self.object_list).splitlines()
      for line_number, line in enumerate(file, start=1):
        logging.debug(f"Import object: {line}")
        tmp = line.lower().rstrip('\r\n').rstrip('\n').split('|')
        logging.debug(f"{tmp=}")

        try:
          level = int(tmp[0])
          prod_lib, dev_lib, target_obj, obj_type, obj_attr = tmp[1:6]
        except ValueError:
          raise Exception(f"Object list: line {line_number} is invalid") from None

        logging.debug(f"{prod_lib=}")
        logging.debug(f"{dev_lib=}")
        logging.debug(f"{target_obj=}")

        obj: do.Deploy_Object = deploy_object_data.create_deploy_object(self.id, level=level, lib=dev_lib, prod_lib=prod_lib, name=target_obj, type=obj_type, attribute=obj_attr)
        self.add_deploy_object(obj)

      logging.info(f"Imported {len(self.deploy_objects)} objects from {self.object_list}")

      self.load_actions_from_json(constants.C_OBJECT_COMMANDS)
      self.save()
      self.copy_object_actions_2_open_stages()
      self.save()

      #os.rename(self.object_list, f"{path}/{self.deploy_version}_{config_file_name}")



    
    def load_actions_from_json(self, file: str):
      obj_cmds = []

      obj_cmds = files.getJson(file)

      for oc in obj_cmds:
        self.deploy_objects.add_object_action_from_dict(dict=oc, workflow=self.workflow)




    def copy_object_actions_2_open_stages(self, stage_id: int|None=None):
      """
      Add object actions to related open stages, right after the step with the same processing step

      Args:
          stage_id (int, optional): Only that stage should get actions
      """

      open_stages = self.get_open_stages()

      if stage_id is not None:
        open_stages = s.Stage_List_list()
        open_stages.append(self.get_open_stages().get_stage(stage_id))

      logging.info(f"Add object ({len(self.deploy_objects)}) actions to stages: {open_stages.get_all_names()}")

      for do in self.deploy_objects:
        
        for do_action in do.actions:
          
          for stage in open_stages:

            if stage.name != do_action.stage:
              continue

            stage_actions = stage.actions.get_actions()

            # The object list can be imported again
            if any(a.processing_step == do_action.processing_step and a.cmd == do_action.cmd for a in stage_actions):
              continue

            same_step = [a for a in stage_actions if a.processing_step == do_action.processing_step]

            copy_action = do_action.get_dict()
            copy_action['id'] = None
            copy_action['deploy_object_id'] = None
            copy_action['run_history'] = []
            stage.actions.add_actions_from_dict(copy_action, add_after=same_step[-1] if len(same_step) > 0 else None)
