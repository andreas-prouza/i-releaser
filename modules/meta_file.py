from __future__ import annotations
import datetime
import json
import configparser
import logging
import re
import os
import sys
from io import StringIO

from enum import Enum

# from pydantic import validate_arguments

from etc import constants, logger_config
from modules import deploy_action as da
from modules import deploy_object as do
from modules import stages as s
from modules import workflow as wf
from modules import ibm_i_commands
from modules import deploy_version as dv
from modules.cmd_status import Status as Cmd_Status
from modules import meta_file_history as mfh


class Meta_file_status(Enum):

  NEW = 'new'
  READY = 'ready'
  IN_PROCESS = 'in_process'
  FAILED = 'failed'
  FINISHED = 'finished'
  CANCELED = 'canceled'
  




class Meta_File:


    #@validate_arguments
    def __init__(self, project:str=None, workflow_name :str=None, workflow=None, file_name=None, create_time=None, update_time=None, status :Meta_file_status=Meta_file_status.NEW, deploy_version : int=None, stages: s.Stage_List_list=None, imported_from_dict=False):

      logging.debug(f"{sys.path=}")

      self.file_name = None
      self.stages = None
      self.status = None
      self.backup_deploy_lib = None
      self.main_deploy_lib = None
      self.create_date = None
      self.create_time = None
      self.commit = None
      self.release_branch = None
      self.project = project
      self.file_name = file_name
      self.deploy_version = deploy_version
      self.run_history = mfh.Meta_File_History_List_list()
      self.activate_history()

#      if imported_from_dict == False:
      self.set_status(status, False)
#      else:
#        self.status = Meta_file_status(status)
        
      self.update_time = update_time
      self.create_time = create_time

      if self.create_time == None:
        self.create_time = str(datetime.datetime.now())

      self.create_date = re.sub(" .*", '', self.create_time)
        
      self.workflow = workflow
      if workflow_name is not None:
        self.workflow = wf.Workflow(name=workflow_name)
      
      if self.project is None:
        self.project = self.workflow.default_project

      self.stages = stages
      if self.stages is None:
        #!!!!!!!!!!!!!!!! Open task: load all stages from workflow, not only the starting one !!!!!!!
        self.stages = s.Stage_List_list(self.workflow)
        
      self.deploy_objects = do.Deploy_Object_List()

      self.actions = da.Deploy_Action_List_list()

      # Set global stages commands for current stages
      #logging.debug(f"Set global stages commands for current stages")
      #if not imported_from_dict:
      #  commands = ibm_i_commands.IBM_i_commands(self)
      #  for stage in self.stages:
      #    logging.debug(f"Set commands for stage '{stage}'")
      #    commands.set_cmds(stage.name)

      if deploy_version == None:
        self.deploy_version = dv.Deploy_Version.get_next_deploy_version(project=self.project, status=self.status)

      self.release_branch = constants.C_GIT_BRANCH_RELEASE.replace('{deploy_version}', str(self.deploy_version)).replace('{project}', self.project)

      if self.file_name == None:
        self.file_name = constants.C_DEPLOY_META_FILE
      self.file_name = os.path.abspath(self.file_name.format(**self.__dict__))

      self.set_deploy_main_lib(f"d{str(self.deploy_version).zfill(9)}")
      self.set_deploy_backup_lib(f"b{str(self.deploy_version).zfill(9)}")

      if not imported_from_dict:
        dv.Deploy_Version.update_deploy_status(self.project, self.deploy_version, self.status, self.file_name, self.commit)
        self.write_meta_file(False)



    def activate_history(self):
      logging.debug(f"Aktivate history log for {self.file_name}")
      logging.debug(f"0. Number of histories: {len(self.run_history)}")

      stdout_new = StringIO()
      history = mfh.Meta_File_History(log=stdout_new)
      self.run_history.add_history(history)

      logging.debug(f"1. Number of histories: {len(self.run_history)}")


      hdl = logging.StreamHandler(stream=stdout_new)
      hdl.setFormatter(logging.root.handlers[0].formatter)
      logging.getLogger().addHandler(hdl)



     #@validate_arguments
    def set_status(self, status, update_meta_file=True):

      logging.debug(f"Set status to {status}")

      if type(status) == str:
        status = Meta_file_status(status)

      logging.debug(f"Update meta file: {update_meta_file}")

      if self.status == Meta_file_status.CANCELED:
        raise Exception("Deployment has been canceled already. It's not possible to change the status!")

      if update_meta_file and status is not Meta_file_status.NEW:
        logging.debug(f"Finished 1.0")
        dv.Deploy_Version.update_deploy_status(self.project, self.deploy_version, status, self.file_name, self.commit)
        logging.debug(f"Finished 1")
        self.status = status
        self.write_meta_file()

      self.status = status
      logging.debug(f"Finished")



     #@validate_arguments
    def set_next_stage(self, from_stage: str):

      if from_stage not in self.stages.get_all_names():
        raise Exception(f"Stage {from_stage} ist not in the list of current stages: {self.stages.get_all_names()}")

      from_stage_obj = self.stages.get_stage(from_stage)
      next_stages = from_stage_obj.get_next_stages_name()

      commands = ibm_i_commands.IBM_i_commands(self)

      # 1. Remove the from_stage from current stages
      # 2. Add next stages to current stages
      # 3. Set global stages commands
      #self.completed_stages.append(from_stage_obj)
      #self.current_stages.remove_stage(from_stage)

      # Not needed, sine all stages exist from the beginning
      # for next_stage in next_stages:

        #self.stages.append(s.Stage.get_stage(self.workflow, next_stage))
        #commands.set_cmds(next_stage)
      
      if self.stages.get_open_stages() == []:
        self.set_status(Meta_file_status.FINISHED)

      self.write_meta_file()



    def run_current_stages(self) -> None:

      names = self.stages.get_runable_stages().get_all_names()
      for name in names:
        self.run_current_stage(name)



     #@validate_arguments
    def run_current_stage(self, stage: str, processing_step: str=None) -> None:
      """Run given stage

      Args:
          stage (str): Stage name
          processing_step (str, optional): Step of stage. Defaults to None.
              If None, all steps will be issued

      Raises:
          Exception: If a processing step was given, which is not in the step list of that stage
      """

      if self.status != Meta_file_status.READY:
        raise Exception(f"Meta file is not in status 'ready', but in status '{self.status.value}'!")
      
      cmd = ibm_i_commands.IBM_i_commands(self)

      runable_stages = self.stages.get_runable_stages(stage)
      logging.debug(f"All runable stages: {runable_stages}")

      if stage not in runable_stages.get_all_names():
        e = Exception(f"Stage '{stage}' is currently not allowed to run!")
        logging.exception(e)
        raise e

      stage_obj = runable_stages.get_stage(stage)
      
      if processing_step is not None and processing_step not in stage_obj.processing_steps:
        e = Exception(f"Processing step '{processing_step}' is not defined in stage '{stage}'. Defined steps are: {stage_obj.processing_steps}")
        logging.exception(e)
        self.write_meta_file()
        raise e

      try:
        self.set_status(Meta_file_status.IN_PROCESS)
      except Exception as err:
        logging.error(err)
        self.write_meta_file()
        raise err
      
      logging.info(f"Run stage {stage}, {processing_step=}")

      try:
        cmd.run_commands(stage=stage_obj, processing_step=processing_step)
      except Exception as err:
        self.set_status(Meta_file_status.FAILED)
        raise err

      self.set_status(Meta_file_status.READY)

      self.check_stage_finish(stage)
      self.check_deployment_finish()




     #@validate_arguments
    def check_stage_finish(self, stage: str) -> None:

      for action in self.actions.get_actions(stage=stage):
        if action.status not in [Cmd_Status.FINISHED, Cmd_Status.FAILED] or (action.status == Cmd_Status.FAILED and action.check_error == True):
          # if stage is not completed, don't set the FINISHED status.
          return

      stage_obj = self.stages.get_stage(stage)
      stage_obj.status = Cmd_Status.FINISHED

      logging.info(f"Stage {stage} has been finished. Setting next stage(s)")
      self.set_next_stage(stage)




     #@validate_arguments
    def check_deployment_finish(self) -> None:

      if len(self.stages.get_open_stages()) == 0:
        logging.info(f"Deployment {self.file_name} has been finished.")
        self.set_status(Meta_file_status.FINISHED)



     #@validate_arguments
    def set_deploy_main_lib(self, library: str):
      self.main_deploy_lib = library.lower()



     #@validate_arguments
    def set_deploy_backup_lib(self, library: str):
      self.backup_deploy_lib = library.lower()



    
    def add_deploy_object(self, object: type[do.Deploy_Object]):

      self.deploy_objects.add_object(object)



    
    def is_backup_name_already_in_use(self, obj_lib: str, obj_name: str, backup_name: str, obj_type: str):
      """
      Parameters
      ----------
      obj_lib : str
          Library name from asking object
      obj_name : str
          Object name from asking object
      backup_name : str, optional
          Suggested backup name which needs to be checked for uniqueness  
      ----------
      """

      for lib in self.deploy_objects:
        for obj in self.deploy_objects[lib]:
          # Check if back-up name is already in use
          if obj['obj_type'] == obj_type and obj.get('backup_name', '') == backup_name:
            return True
          
          # Check if back-up name is already used as object name
          if (not (lib == obj_lib and 
                  obj['obj_type'] == obj_type and 
                  obj['obj_name'] == obj_name) and 
             obj['obj_type'] == obj_type and 
             obj['obj_name'] == backup_name):
            return True

      return False



    def set_deploy_objects(self, objects: []):

      for obj in objects:
        self.add_deploy_object(do.Deploy_Object(dict=obj))



    
    def get_actions(self, processing_step: str=None, stage: str=None) -> []:

      list=[]

      if stage is None:
        raise Exception(f"Stage is None")

      list=self.stages.get_stage(stage).actions.get_actions(processing_step=processing_step)

      #for a in self.actions:
      #  if processing_step is None or a.processing_step == processing_step:
          # Consider stage if given
      #    if stage is not None and a.stage is not None and stage != a.stage:
      #      continue
      #    list.append(a)
      
      list = list + self.deploy_objects.get_actions(processing_step=processing_step, stage=stage)
      
      return list



    def get_next_open_action(self, processing_step: str=None, stage: str=None):
      for action in self.get_actions(processing_step=processing_step, stage=stage):
        if action.status == Cmd_Status.FINISHED or (action.status == Cmd_Status.FAILED and action.check_error == False):
          continue
        return action
      


    @DeprecationWarning
    def get_actions_as_dict(self, processing_step: str=None, stage: str=None):

      actions = self.actions.get_actions_as_dict(processing_step=processing_step, stage=stage)
      sorted_action_steps = {}

      for st,ps in actions.items():
        if st in self.stages.get_all_names():
          sorted_stage_steps = self.stages.get_stage(st).processing_steps
        
        for sorted_stage_step in sorted_stage_steps:
          for p in ps:
            if p['processing_step'] == sorted_stage_step:
              if st in sorted_action_steps.keys():
                sorted_action_steps[st].append(p)
                continue

              sorted_action_steps[st] = [p]
      
      return sorted_action_steps



    def load_json_file(file_name: str) -> Meta_File:

      logging.debug(f"Load meta file {file_name}")

      with open (file_name, "r") as file:
        meta_file_json=json.load(file)
        
        workflow = wf.Workflow(name=meta_file_json['general']['workflow']['name'])
        meta_file = Meta_File(workflow=workflow,
                              project=meta_file_json['general']['project'],
                              deploy_version=meta_file_json['general']['deploy_version'],
                              status=meta_file_json['general']['status'],
                              file_name=f"{meta_file_json['general']['file_name']}",
                              create_time=meta_file_json['general']['create_time'],
                              update_time=meta_file_json['general']['update_time'],
                              stages=s.Stage_List_list(workflow=workflow,iterable=meta_file_json['general']['stages']),
                              imported_from_dict=True
                             )
        meta_file.commit=meta_file_json['general']['commit']
        meta_file.release_branch=meta_file_json['general']['release_branch']

        meta_file.set_deploy_objects(meta_file_json['objects'])
        meta_file.set_deploy_main_lib(meta_file_json['deploy_libs']['main_lib'])
        meta_file.set_deploy_backup_lib(meta_file_json['deploy_libs']['backup_lib'])
        #meta_file.actions.add_actions_from_list(meta_file_json['deploy_cmds'])
        
        meta_file.run_history.add_historys_from_list(meta_file_json['run_history'])

        #meta_file.write_meta_file()

        return meta_file
      
      raise Exception(f"Meta file {file_name} does not exist")



    def cancel_deployment(self):
      self.set_status(Meta_file_status.CANCELED)
      logging.info('Deployment has been canceled!')
      self.write_meta_file()


    # Load meta file based on its version number
    def load_version(project:str, version: int) -> Meta_File:

      deployment = dv.Deploy_Version.get_deployment(project, version)

      if deployment is None or 'meta_file' not in deployment:
        raise Exception(f"Couldn't find deployment version {version}: {project=}, {deployment=}")

      return Meta_File.load_json_file(deployment['meta_file'])



    def get_all_data_as_dict(self) -> {}:

      dict = {}
      dict['general'] = {'workflow':        self.workflow.get_dict(),
                         'project':         self.project,
                         'deploy_version':  self.deploy_version,
                         'file_name':       self.file_name,
                         'commit':          self.commit,
                         'release_branch':  self.release_branch,
                         'create_time':     self.create_time,
                         'update_time':     self.update_time,
                         'status':          self.status.value,
                         'stages':  self.stages.get_dict(),
                        }
      dict['deploy_libs'] = {'main_lib':    self.main_deploy_lib,
                             'backup_lib':  self.backup_deploy_lib,
                            }
      #dict['deploy_cmds'] = self.get_actions_as_dict()
      dict['objects'] = self.deploy_objects.get_objectjs_as_dict()
      dict['run_history'] = self.run_history.get_list()
      logging.debug(f"Number of histories: {len(self.run_history)}")

      return dict



    def __eq__(self, o):
      s=self
      result = s.actions == o.actions
      result = s.deploy_objects == o.deploy_objects
      result = s.stages == o.stages

      if (s.status, s.project, s.deploy_version, s.update_time, s.create_time, s.file_name, s.commit, s.release_branch, s.stages, s.deploy_objects, s.backup_deploy_lib, s.main_deploy_lib, s.actions) == \
         (o.status, o.project, o.deploy_version, o.update_time, o.create_time, o.file_name, s.commit, s.release_branch, o.stages, o.deploy_objects, o.backup_deploy_lib, o.main_deploy_lib, o.actions):
        return True
      return False



    
    def write_meta_file(self, update_time: bool=True):

      if update_time:
        self.update_time = str(datetime.datetime.now())

      file_dir = os.path.dirname(os.path.realpath(self.file_name))
      if not os.path.isdir(file_dir):
        os.makedirs(file_dir)

      logging.debug(f"Save meta file to {self.file_name}")
      
      with open(self.file_name, 'w') as file:
        json.dump(self.get_all_data_as_dict(), file, default=str, indent=4)



    
    def add_object_from_meta_structure(self, objects: [], object_type: str):

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

      #self.write_meta_file()


    
    def import_objects_from_config_file(self, config_file: str):

      logging.debug(f"File: {os.path.abspath(config_file)}")

      with open(config_file, "r") as file:
        for line in file:
          logging.debug(f"Import object: {line}")
          tmp = line.lower().rstrip('\r\n').rstrip('\n').split('|')
          prod_obj = re.split(r"/|\.", tmp[2])
          target_obj = tmp[3].split('/')
          logging.debug(f"{tmp=}")
          logging.debug(f"{prod_obj=}")
          logging.debug(f"{target_obj=}")
          obj = do.Deploy_Object(lib=target_obj[0], prod_lib=prod_obj[0], name=prod_obj[1], type=prod_obj[3], attribute=prod_obj[2])
          self.add_deploy_object(obj)
      
      self.load_actions_from_json(constants.C_OBJECT_COMMANDS)

      config_file_name = os.path.basename(config_file)
      path = os.path.dirname(os.path.realpath(self.file_name))

      os.rename(config_file, f"{path}/{self.deploy_version}_{config_file_name}")



    
    def load_actions_from_json(self, file: str):
      obj_cmds = []

      with open(file, "r") as file:
        obj_cmds = json.load(file)

      for stage in self.stages.get_open_stages().get_all_names():
        for oc in obj_cmds:
          self.deploy_objects.add_object_action_from_dict(dict=oc, stage=stage)
      
      #self.write_meta_file()


