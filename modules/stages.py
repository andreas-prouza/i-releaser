from __future__ import annotations
import json
import datetime
import logging

# from pydantic import validate_arguments

from etc import constants
from modules import workflow as wf
from modules.cmd_status import Status as Cmd_Status
from modules import deploy_action as da, workflow


from enum import Enum


class Actions(Enum):

  RUN_STAGE = 'run_stage'
  SET_CHECK_ERROR = 'set_check_error'
  



class Stage:

  # Static id counter for each stage to be unique
  id=0

  def __init__(self, dict: {}={}):
    self.id :int = None
    self.workflow = None
    self.name :str = None
    self.description :str = None
    self.host :str = None
    self.remote_dir :str = None
    self.build_dir :str = None
    self.next_stages :Stage_List_list = Stage_List_list()
    self.next_stage_ids :[int] = []
    self.after_stages_finished :[str] = []
    self.from_stage_id = None
    self.clear_files = None
    self.lib_replacement_necessary = None
    self.lib_mapping = []
    self.processing_steps = []
    self.actions = da.Deploy_Action_List_list()
    self.execute_remote = None
    self.status = Cmd_Status.NEW
    self.create_time = str(datetime.datetime.now())
#    self.create_time = '2023-03-04 14:31:30.404775'
    self.update_time = None
    self.processing_users :[str] = []


    if len(list(set(dict.keys()) - set(self.__dict__.keys()))) > 0 and len(dict) > 0:
      e = Exception(f"Attributes of {type(self)} ({self.__dict__}) does not match attributes from {dict=}")
      logging.exception(e, stack_info=True)
      raise e

    if len(list(set(dict.keys()) - set(self.__dict__.keys()))) == 0:
      
      for k, v in dict.items():
        setattr(self, k, v)

    if self.id is None:
      Stage.id += 1
      self.id = Stage.id


  def set_status(self, status, update_time=True):

    if (type(status) == str):
      status = Cmd_Status(status)
    self.status = status
    if update_time:
      self.update_time = str(datetime.datetime.now())
#    self.update_time = '2023-03-04 14:31:30.404775'



  def set_processing_steps(self, workflow: wf.Workflow):
    """Set all actions which are allowed for this stage

    Args:
        stage (str): Name of stage
    """

    #get all processing steps for given stage
    do_steps = self.processing_steps

    wf_steps = wf.Workflow.get_workflow_steps_mapping(workflow_dict=workflow.get_dict())
    
    all_steps = {x['processing_step']:x for x in wf_steps}.values()

    for step in do_steps:

      for all_step in all_steps:
        if step == all_step['processing_step']:
          self.actions.add_action_cmd(
                cmd=all_step['execute'], 
                environment=da.Command_Type(all_step.get('environment')), 
                processing_step=all_step.get('processing_step', []), 
                stage=self.name, 
                check_error=all_step.get('check_error', True), 
                execute_remote=all_step.get('execute_remote', None)
          )
          break



  def get_stage_from_workflow(workflow:workflow.Workflow, stage_name: str) -> Stage:
    """Retrieves stage from workflow
        This is also a check if the wanted stage exist in the workflow config

    Args:
        workflow (str): Name of workflow
        name (str): Name of stage

    Raises:
        Exception: If given stage does not exist in workflow cofig

    Returns:
        Stage: Stage object
    """
    
    stage = workflow.get_stage(stage_name)
    
    if stage is not None:
      
      stage = Stage.get_stage_from_dict(workflow, stage)
      stage.set_processing_steps(workflow)
      
      if len(stage.actions) < len(stage.processing_steps):
        raise Exception(f"{stage_name}: {len(stage.actions)=} is less than {len(stage.processing_steps)=}")

      return stage

    e = Exception(f"No stage found with '{workflow.name=}' & '{stage_name=}' in '{constants.C_WORKFLOW}'")
    logging.exception(e, stack_info=True)
    raise e



  def get_stage_from_dict(wf:workflow.Workflow, dict: {}={}):

    stage = Stage()

    Stage.validate(dict)

    for k, v in dict.items():
      setattr(stage, k, v)

    stage.set_status(stage.status, False)
    stage.actions = da.Deploy_Action_List_list(stage.actions)
    stage.next_stages = Stage_List_list(wf, stage.next_stages)

    return stage



  def get_dict(self) -> {}:
    return {
      'id' : self.id,
      'name' : self.name,
      'description' : self.description,
      'host' : self.host,
      'remote_dir' : self.remote_dir,
      'build_dir' : self.build_dir,
      'next_stages' : self.next_stages.get_all_names(),
      'next_stage_ids': self.next_stage_ids,
      'after_stages_finished': self.after_stages_finished,
      'clear_files' : self.clear_files,
      'processing_steps' : self.processing_steps,
      'execute_remote' : self.execute_remote,
      'lib_replacement_necessary' : self.lib_replacement_necessary,
      'lib_mapping' : self.lib_mapping,
      'status' : self.status.value,
      'create_time' : self.create_time,
      'update_time' : self.update_time,
      'processing_users' : self.processing_users,
      'actions' : self.actions.get_actions_as_dict(),
    }



  def get_next_stages(self) -> Stage_List_list:

    new_next_stages = Stage_List_list()
    
    for next_stage in self.next_stages:
      new_next_stages.append(next_stage)

    return new_next_stages



  def get_next_stages_name(self) -> []:

    new_next_stages = []
    
    for next_stage in self.next_stages:
      new_next_stages.append(next_stage.name)

    return new_next_stages



  def validate(stage_dict: {}):

    if 'name' not in stage_dict.keys():
      raise Exception(f"Stage name has to be defined: {stage_dict=}")

    for key in stage_dict.keys():
      if key not in ['id', 'name', 'description', 'host', 'build_dir', 'remote_dir', 'next_stages', 'next_stage_ids', 'after_stages_finished', 'from_stage_id', 'clear_files', 'processing_steps', 'execute_remote', 'lib_replacement_necessary', 'processing_users', 'lib_mapping', 'status', 'create_time', 'update_time', 'actions']:
        raise Exception(f"Attribute {key} is invalid for stage {stage_dict['name']}!")
    
    
    if 'next_stages' in stage_dict.keys() and stage_dict['next_stages'] is not None:
      if type(stage_dict['next_stages']) != list:
        raise Exception(f"Key 'next_stages' has to be a list[] in stage {stage_dict=}")
    
    if 'processing_steps' in stage_dict.keys() and stage_dict['processing_steps'] is not None:
      if type(stage_dict['processing_steps']) != list:
        raise Exception(f"Key 'processing_steps' has to be a list[] in stage {stage_dict=}")
    
    if 'clear_files' in stage_dict.keys() and stage_dict['clear_files'] is not None:
      if type(stage_dict['clear_files']) != bool:
        raise Exception(f"Key 'clear_files' has to be a bool in stage {stage_dict=}")

    stage = Stage()

    if len(list(set(stage_dict.keys()) - set(stage.__dict__.keys()))) > 0:
      raise Exception(f"Attributes from parameter {stage_dict} does not match with class attributes. \
        Unknown attribute(s) are: {list(set(stage_dict.keys()) - set(stage.__dict__.keys()))}")



  def __eq__(self, other):
    logging.debug('equals 2 stages')
 #   other.next_stages !!! ist das Problem
    if (self.id, self.description, self.host, self.remote_dir, self.build_dir, self.next_stages.get_all_names(), self.clear_files, self.processing_steps, self.processing_users, self.lib_replacement_necessary, self.lib_mapping, self.status, self.create_time, self.update_time, self.actions, self.after_stages_finished, self.execute_remote) == \
       (other.id, other.description, other.host, other.remote_dir, other.build_dir, other.next_stages.get_all_names(), other.clear_files, other.processing_steps, other.processing_users, other.lib_replacement_necessary, other.lib_mapping, other.status, other.create_time, other.update_time, other.actions, other.after_stages_finished, other.execute_remote):
      return True

    logging.warn(f"{self.id} - {self.description} - {self.host} - {self.remote_dir} - {self.build_dir} - {self.next_stages.get_all_names()} - {self.clear_files} - {self.processing_steps} - {self.processing_users} - {self.lib_replacement_necessary} - {self.lib_mapping} - {self.status} - {self.create_time} - {self.update_time} - {self.actions} - {self.after_stages_finished=} - {self.execute_remote=}")
    logging.warn(f"{other.id} - {other.description} - {other.host} - {other.remote_dir} - {other.build_dir} - {other.next_stages.get_all_names()} - {other.clear_files} - {other.processing_steps} - {other.processing_users} - {other.lib_replacement_necessary} - {other.lib_mapping} - {other.status} - {other.create_time} - {other.update_time} - {other.actions} - {other.after_stages_finished=} - {other.execute_remote=}")

    return False





class Stage_List_list(list):

    def __init__(self, workflow:workflow.Workflow=None, iterable=None):
      """Generates a list of stages for a workflow

      Args:
          workflow (workflow.Workflow, optional): If given, get stages based on workflow stages dict
          iterable (list, optional): List can contains 2 types:

              * str
                Stage object will be retrieved from workflow based on stage name

              * dict
                Stage object will be generated based on existing dict
      """

      # This is only not to change the original parameter
      iterable2 = []
      stage_list = []

      #if (iterable is not None and workflow is None) or (iterable is None and workflow is not None):
      #  raise Exception(f'Missing parameter to get the list data: {iterable=}, {workflow=}')

      if iterable is not None and len(iterable) > 0 and workflow is not None:
        for i, s in enumerate(iterable):
          iterable2.append(s)
          if type(s) == str:
             iterable2[i] = Stage.get_stage_from_workflow(workflow, s)
          if type(s) == dict:
             iterable2[i] = Stage.get_stage_from_dict(workflow, s)
          stage_list.append(iterable2[i].name)
             

      if workflow is not None and iterable is None:

        for stage in  workflow.stages:
          
          if stage['name'] in stage_list:
            continue

          logging.debug(f"Got stage from workflow: {stage=}")
          additional_stage = Stage.get_stage_from_workflow(workflow, stage['name'])
          iterable2.append(additional_stage)
          stage_list.append(additional_stage.name)

      if len(iterable2) > 0:
        super().__init__(iterable2)
        return

      super().__init__()



    def __setitem__(self, index, item):
        super().__setitem__(index, self._validate_item(item))



    def insert(self, index, item):
        super().insert(index, self._validate_item(item))

    def append(self, item):

        # if stage already exist, just reopen it
        for stage in self:
          if item.id == stage.id:
            raise Exception(f"Stage {item.name} (id {item.id}) already exist")

        super().append(self._validate_item(item))

    def extend(self, other):
        if isinstance(other, type(Stage())):
            super().extend(other)
        else:
            super().extend(self._validate_item(item) for item in other)

    def _validate_item(self, value):
        if type(value) == Stage:
            return value
        raise TypeError(
            f"{Stage} value expected, got {type(value).__name__}"
        )


    def validate_items(dict: []) -> None:

      for item in dict:
        Stage.validate(item)

        

    def get_all_names(self) ->[]:
      list = []

      for s in self:
        list.append(s.name)

      return list


    def get_all_ids(self) ->[]:
      list = []

      for s in self:
        list.append(s.id)

      return list



    def get_dict(self) -> {}:
      list = []

      for s in self:
        list.append(s.get_dict())

      return list



    def get_stage(self, id: int) -> Stage:

      if type(id) == str:
        id = int(id)

      if type(id) != int:
        raise Exception(f"Parameter is not a number: {id}")

      for s in self:
        if s.id == id:
          return s

      raise Exception(f"Stage id {id} not found in list {self.get_all_ids()}")
      return None



    def get_stages_by_name(self, stage_name: str) -> [Stage_List_list]:

      stages = Stage_List_list()

      for s in self:
        if s.name == stage_name:
          stages.append(s)

      return stages



    def get_stage_list_by_status(self, status: Cmd_Status) -> []:

      stages = Stage_List_list()

      for s in self:
        if s.status == status:
          stages.append(s)

      return stages




    def remove_stage(self, id: int) -> None:

      for i, o in enumerate(self):
        if o.id == id:
          del self[i]
          return

