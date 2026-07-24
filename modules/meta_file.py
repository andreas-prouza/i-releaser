import datetime
import configparser
import logging
import os
from io import StringIO

import threading

# from pydantic import validate_arguments

from etc import constants
from modules import action_type, deploy_action as da, files, permissions, stage_status
from modules import deploy_object as do
from modules import stages as s
from modules import workflow as wf
from modules import deploy_version as dv
from modules.cmd_status import Status as Cmd_Status
from modules import meta_file_history as mfh
from modules.db import meta_file_history_data as mfhd, processing_user_data
from modules.db import deploy_object_data
from modules.permission_config import check_user_permission

from modules.meta_file_status import Meta_file_status


class StageNotReadyException(Exception):
  pass



class Meta_File:
    
    CURRENT_USER = None

    """
    Meta_File describes a information of a deployment
    It's the main controller
    """



    def __init__(self, project: str|None=None, workflow_name : str|None=None, workflow=None, 
                object_list=None, create_time=None, update_time=None, status :Meta_file_status=None, 
                deploy_version : int|None=None, deploy_version_id : int|None=None, stages: s.Stage_List_list=None,
                processing_users: list=None, custom_data: dict=None,
                id: int|None=None, meta_dir: str|None=None):

      #logging.debug(f"{sys.path=}")

      self.id: int = id
      self.stages: s.Stage_List_list = stages or s.Stage_List_list()
      self.current_running_stage = None
      self.status: Meta_file_status = status or Meta_file_status.NEW

      self.backup_deploy_lib = None
      self.main_deploy_lib = None
      self.remote_deploy_lib = None
      self.commit = None
      self.release_branch = None
      self.project: str = project
      self.deploy_version: int = deploy_version
      self.deploy_version_id: int = deploy_version_id
      self.object_list: str = object_list
      self.run_history: mfh.Meta_File_History_List_list = mfh.Meta_File_History_List_list()
      self.processing_users: list = processing_users or []
      self.custom_data = custom_data or {}
        
      self.update_time: datetime.datetime = update_time or datetime.datetime.now()
      self.create_time: datetime.datetime = create_time or datetime.datetime.now()

      if isinstance(self.update_time, str):
        self.update_time = datetime.datetime.fromisoformat(self.update_time)

      if isinstance(self.create_time, str):
        self.create_time = datetime.datetime.fromisoformat(self.create_time)

      if self.create_time == None:
        self.create_time = datetime.datetime.now()
        self.update_time = self.create_time

      self.meta_dir: str = meta_dir
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



    def activate_history(self):
      #logging.debug(f"Aktivate history log for {self.deploy_version}")
      #logging.debug(f"0. Number of histories: {len(self.run_history)}")

      stdout_new = StringIO()
      history: mfh.Meta_File_History = mfhd.create_new_meta_file_history(log=stdout_new, meta_file_id=self.id)
      self.run_history.append(history)

      hdl = logging.StreamHandler(stream=stdout_new)
      hdl.setFormatter(logging.root.handlers[0].formatter)
      logging.getLogger().addHandler(hdl)



    def save(self, update_meta_file=True):
        """Saves the current state of the meta file to the database."""
        if not update_meta_file:
          logging.warning("Update meta file is set to False. Meta file will not be saved")
          return
            
        self.update_time = datetime.datetime.now()
        from modules.db import meta_file_data
        meta_file_data.save_meta_file(self)
        

    def set_status(self, status, update_meta_file=True):

      logging.debug(f"Set status to {status}")

      if type(status) == str:
        status = Meta_file_status(status)

      logging.debug(f"Update meta file: {update_meta_file}")

      if self.status == Meta_file_status.CANCELED:
        raise Exception("Deployment has been canceled already. It's not possible to change the status!")

      if update_meta_file and status is not Meta_file_status.NEW:
        logging.debug(f"Update meta file: Finished 1.0")
        dv.Deploy_Version.update_deploy_status(self.project, self.deploy_version, status, self.commit)
        logging.debug(f"Update meta file: Finished 1")
        self.status = status
        self.save()

      self.status = status
      logging.debug(f"Finished meta file status set to {self.status.value}")




    #@check_user_permission(permissions.PermissionAction.CHANGE_CHECK_ERROR)
    def set_action_check(self, stage_id: int, action_id: int, check: bool, current_user: str) -> None:
      stage = self.get_open_stages().get_stage(stage_id)

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
            es.status = stage_status.Status.READY
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
      
      logging.debug(f'{self.stages.summary()=}')
      if len(self.get_open_stages()) == 0:
        self.set_status(Meta_file_status.FINISHED)

      self.save()



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
        next_stages.append(self.get_stage_by_id(next_id))

      logging.debug(f"Next stages for {from_stage.name} ({from_stage.id}): {next_stages.get_all_ids}")
      if len(next_stages) > 0:
        return next_stages

      logging.debug(f"Next stages 2 for {from_stage.name}: {from_stage}")
      for ns in from_stage.next_stages:
        new_stage = self.get_open_stages().get_stages_by_name(stage_name=ns)[0]
        next_stages.append(new_stage)
      return next_stages




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

      import threading
      t = threading.Thread(target=self.run_current_stage, args=(stage_id, processing_step, continue_run))
      t.start()
      return t



    def check_deployment_ready_2_run(self, stage_id: int, processing_step: str|None=None):

      if self.status != Meta_file_status.READY:
        raise Exception(f"Meta file is not in status 'ready', but in status '{self.status.value}'!")
      
      runable_stage = self.get_open_stages().get_stage(id=stage_id)
      
      if runable_stage is None:
        e = Exception(f"Stage id '{stage_id}' is not available to run!")
        logging.exception(e, stack_info=True)
        raise e
  
      if processing_step is not None and processing_step not in runable_stage.processing_steps:
        e = Exception(f"Processing step '{processing_step}' is not defined in stage '{runable_stage.name}' (id {runable_stage.id}). Defined steps are: {runable_stage.processing_steps}")
        logging.exception(e, stack_info=True)
        self.save()
        raise e

      waiting_for_stages = self.get_stages_needs_2_get_finished(runable_stage)
      if len(waiting_for_stages) > 0:
        e = StageNotReadyException(f"Stage {runable_stage.name} ({stage_id}) is still waiting for other stages to get finished: {waiting_for_stages}")
        logging.exception(e, stack_info=True)
        raise e

      dv.Deploy_Version.validate_deployment(self.project, self.deploy_version, Meta_file_status.IN_PROCESS)




    #@check_user_permission(permissions.PermissionAction.RUN_WORKFLOW)
    def run_current_stage(self, stage_id: int, processing_step: str|None=None, continue_run=True) -> None:
      """Run given stage

      Args:
          stage_id (int): Stage id
          processing_step (str, optional): Step of stage. Defaults to None.
              If None, all steps will be issued
          continue_run (bool, optional):
              True: Continiue from first step which has not been finished
              False: Run all steps from this stage, even if they already have been finished successful

      Raises:
          Exception: If a processing step was given, which is not in the step list of that stage
      """
      logging.debug(f"Run current stage with id {stage_id} and processing step {processing_step}")

      self.check_deployment_ready_2_run(stage_id=stage_id, processing_step=processing_step)
      logging.debug('Check passed')

      try:
        logging.debug("Set meta file status to 'in process'")
        self.set_status(Meta_file_status.IN_PROCESS)
      except Exception as err:
        logging.exception(err, stack_info=True)
        self.save()
        raise err

      runable_stage = self.get_open_stages().get_stage(id=stage_id)
      logging.debug(f"Runable stage: {runable_stage.name} ({runable_stage.id}) with processing step {processing_step}")

      from modules.ibm_i_commands import IBM_i_commands
      logging.debug(f"Create IBM i commands instance")
      cmd = IBM_i_commands(self)
      
      logging.info(f"Run stage {runable_stage.name} (id {runable_stage.id}), {processing_step=}")

      self.current_running_stage = runable_stage

      try:
        cmd.run_commands(stage=runable_stage, processing_step=processing_step, continue_run=continue_run)
      except Exception as err:
        logging.exception(err, stack_info=True)
        self.set_status(Meta_file_status.FAILED)
        raise err

      logging.info(f"All actions completed '{runable_stage.name}'")
      logging.info(f"Set meta file status to '{Meta_file_status.READY}'")

      self.check_stage_finish(runable_stage)

      self.set_status(Meta_file_status.READY)

      self.check_deployment_finish()
      logging.info(f"Finished run of stage '{runable_stage.name}'")




    def check_stage_finish(self, stage: s.Stage) -> None:

      logging.debug("Check if stage has been finished")
      
      for action in stage.actions:

        if action.status not in [Cmd_Status.FINISHED, Cmd_Status.FAILED] or (action.status == Cmd_Status.FAILED and action.check_error == True):

          logging.info(f"Action {action.id} is in status '{action.status}'. So stage is not finished yet")
          # if stage is not completed, don't set the FINISHED status.
          return

      stage.status = stage_status.Status.FINISHED

      logging.info(f"Stage {stage.name} ({stage.id}) has been finished. Setting next stage(s) {stage.next_stages}")
      self.set_next_stage(stage)



    def check_deployment_finish(self) -> None:

      if self.get_open_stages() is None or len(self.get_open_stages()) == 0:
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





    
    def is_backup_name_already_in_use(self, lib: str, name: str, backup_name: str, type: str):
      """
      Parameters
      ----------
      lib : str
          Library name from asking object
      name : str
          Object name from asking object
      backup_name : str, optional
          Suggested backup name which needs to be checked for uniqueness  
      type : str
          Object type from asking object
      ----------
      """

      for lib in self.deploy_objects:
        for obj in self.deploy_objects[lib]:
          # Check if back-up name is already in use
          if obj['type'] == type and obj.get('backup_name', '') == backup_name:
            return True
          
          # Check if back-up name is already used as object name
          if not (lib == lib and obj['type'] == type and obj['name'] == name) and obj['type'] == type and obj['name'] == backup_name:
            return True

      return False



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



    def get_stages_by_name(self, stage: str) -> s.Stage:

      if self.get_open_stages() is not None and stage in self.get_open_stages().get_all_names():
        return self.get_open_stages().get_stages_by_name(stage)

      if self.get_processed_stages() is not None and stage in self.get_processed_stages().get_all_names():
        return self.get_processed_stages().get_stages_by_name(stage)


    
    def get_actions(self, processing_step: str|None=None, stage_id: int|None=None, action_id: int|None=None, include_subactions: bool=True) -> list[da.Deploy_Action]:

      list: list[da.Deploy_Action]=[]

      if stage_id is None:
        raise Exception(f"Stage id is None")

      stage_obj = self.get_stage_by_id(stage_id)

      list=stage_obj.actions.get_actions(processing_step=processing_step, action_id=action_id, include_subactions=include_subactions)
      
      list = list + self.deploy_objects.get_actions(processing_step=processing_step, stage=stage_obj.name, action_id=action_id, include_subactions=include_subactions)
      
      return list



#    def get_next_open_action(self, processing_step: str|None=None, stage: str|None=None):
#      for action in self.get_actions(processing_step=processing_step, stage=stage):
#        if action.status == Cmd_Status.FINISHED or (action.status == Cmd_Status.FAILED and action.check_error == False):
#          continue
#        return action
      





    #@check_user_permission(permissions.PermissionAction.CANCEL_WORKFLOW)
    def cancel_deployment(self):
      self.set_status(Meta_file_status.CANCELED)
      logging.info('Deployment has been canceled!')
      self.save()



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
                        }
      dict['deploy_libs'] = {'main_lib':    self.main_deploy_lib,
                             'remote_lib':  self.remote_deploy_lib,
                             'backup_lib':  self.backup_deploy_lib,
                            }
      #dict['deploy_cmds'] = self.get_actions_as_dict()
      dict['processing_users'] = self.processing_users
      dict['objects'] = self.deploy_objects.get_objects_as_list_of_dict()
      dict['run_history'] = self.run_history.get_list()
      dict['custom_data'] = self.custom_data
      logging.debug(f"Number of histories: {len(self.run_history)}")

      return dict



    def __eq__(self, o):
      s=self
      result = s.deploy_objects == o.deploy_objects
      result = s.get_open_stages() == o.get_open_stages()
      result = s.get_processed_stages() == o.get_processed_stages()

      if (s.status, s.project, s.deploy_version, s.update_time, s.create_time, s.object_list, s.commit, s.release_branch, s.get_processed_stages(), s.get_deploy_objects(), s.backup_deploy_lib, s.main_deploy_lib) == \
         (o.status, o.project, o.deploy_version, o.update_time, o.create_time, o.object_list, s.commit, s.release_branch, o.get_processed_stages(), o.get_deploy_objects(), o.backup_deploy_lib, o.main_deploy_lib):
        return True
      return False



    
    def add_object_from_meta_structure(self, objects: list[str], object_type: str):

      for obj in objects:

          if '/' not in obj:
              continue

          obj = obj.split('/')
          deploy_obj = do.Deploy_Object(lib=obj[0], name=obj[1], type=object_type)

          self.add_deploy_object(deploy_obj)



    
    def import_objects_from_config_file_old(self, config_file: str):

      object_config = configparser.ConfigParser()
      object_config.read(config_file, encoding='UTF-8')

      obj_list = dict(object_config.items('OBJECTS'))
      for obj_type in obj_list:
          self.add_object_from_meta_structure(obj_list[obj_type].split(' '), obj_type)

      #self.save()


    
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

      self.deploy_objects = do.Deploy_Object_List()

      if self.object_list is None:# and not os.path.exists(constants.C_OBJECT_LIST):
        e = Exception(f"No object list defined. No objects will be imported. {self.object_list=}")
        logging.exception(e, stack_info=True)
        raise e
      
      logging.debug(f"Abs. file: {os.path.abspath(self.object_list)}")

      if not os.path.exists(self.object_list):
        raise Exception(f"Object list {self.object_list} does not exist")

      logging.debug(f"File: {self.object_list}")

      file = files.readFile(self.object_list).splitlines()
      for line in file:
        logging.debug(f"Import object: {line}")
        tmp = line.lower().rstrip('\r\n').rstrip('\n').split('|')
        logging.debug(f"{tmp=}")
        level = int(tmp[0])
        prod_lib = tmp[1]
        dev_lib = tmp[2]
        target_obj = tmp[3]
        obj_type = tmp[4]
        obj_attr = tmp[5]
        logging.debug(f"{prod_lib=}")
        logging.debug(f"{dev_lib=}")
        logging.debug(f"{target_obj=}")

        obj: do.Deploy_Object = deploy_object_data.create_deploy_object(self.id, level=level, lib=dev_lib, prod_lib=prod_lib, name=target_obj, type=obj_type, attribute=obj_attr)
        self.add_deploy_object(obj)

      logging.info(f"Imported {len(self.deploy_objects)} objects from {self.object_list}")

      self.load_actions_from_json(constants.C_OBJECT_COMMANDS)
      self.save()

      #os.rename(self.object_list, f"{path}/{self.deploy_version}_{config_file_name}")



    
    def load_actions_from_json(self, file: str):
      obj_cmds = []

      obj_cmds = files.getJson(file)

      for oc in obj_cmds:
        self.deploy_objects.add_object_action_from_dict(dict=oc, workflow=self.workflow)




    def copy_object_actions_2_open_stages(self, stage_id: int|None=None):
      """
      Add object actions to related open stages

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
          
          for os in open_stages:

            if os.name == do_action.stage:
              copy_action = do_action.get_dict()
              copy_action['id'] = None
              os.actions.add_actions_from_dict(copy_action)
