from __future__ import annotations
import json
import datetime
import logging

# from pydantic import validate_arguments

from etc import constants
from modules import workflow as wf
from modules.cmd_status import Status as Cmd_Status



class Stage:


  def __init__(self, dict: {}={}):
    self.workflow = None
    self.name = None
    self.description = None
    self.host = None
    self.base_dir = None
    self.build_dir = None
    self.next_stages = Stage_List_list()
    self.clear_files = None
    self.lib_replacement_necessary = None
    self.lib_mapping = []
    self.processing_steps = []
    self.status = Cmd_Status.NEW
    self.create_time = str(datetime.datetime.now())
#    self.create_time = '2023-03-04 14:31:30.404775'
    self.update_time = None


    if len(list(set(dict.keys()) - set(self.__dict__.keys()))) > 0 and len(dict) > 0:
      raise Exception(f"Attributes of {type(self)} ({self.__dict__}) does not match attributes from {dict=}")

    if len(list(set(dict.keys()) - set(self.__dict__.keys()))) == 0:
      
      for k, v in dict.items():
        setattr(self, k, v)


  def set_status(self, status, update_time=True):

    if (type(status) == str):
      status = Cmd_Status(status)
    self.status = status
    if update_time:
      self.update_time = str(datetime.datetime.now())
#    self.update_time = '2023-03-04 14:31:30.404775'



  def get_stage(workflow_name:str, stage_name: str) -> Stage:
    """Retrieves stage from workflow
        This is also a check if the wanted stage exist in the workflow config

    Args:
        workflow (str): Name of workflow
        name (str): Name of stage

    Raises:
        Exception: If give stage does not exist in workflow cofig

    Returns:
        Stage: Stage object
    """
    
    stage = wf.Workflow.get_workflow_stage(workflow_name, stage_name)
    
    if stage is not None:
      return Stage.get_stage_from_dict(workflow_name, stage)

    raise Exception(f"No stage found with '{workflow_name=}' & '{stage_name=}' in '{constants.C_WORKFLOW}'")



  def get_stage_from_dict(workflow:str, dict: {}={}):

    stage = Stage()

    Stage.validate(dict)

    for k, v in dict.items():
      setattr(stage, k, v)

    stage.set_status(stage.status, False)
    
    stage.next_stages = Stage_List_list(workflow, stage.next_stages)

    return stage



  def get_dict(self) -> {}:
    return {
      'name' : self.name,
      'description' : self.description,
      'host' : self.host,
      'base_dir' : self.base_dir,
      'build_dir' : self.build_dir,
      'next_stages' : self.next_stages.get_all_names(),
      'clear_files' : self.clear_files,
      'processing_steps' : self.processing_steps,
      'lib_replacement_necessary' : self.lib_replacement_necessary,
      'lib_mapping' : self.lib_mapping,
      'status' : self.status.value,
      'create_time' : self.create_time,
      'update_time' : self.update_time,
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

    for key in stage_dict.keys():
      if key not in ['name', 'description', 'host', 'build_dir', 'base_dir', 'next_stages', 'clear_files', 'processing_steps', 'lib_replacement_necessary', 'lib_mapping', 'status', 'create_time', 'update_time']:
        raise Exception(f"Attribute {key} is invalid for a stage!")
    
    stage = Stage()

    if len(list(set(stage_dict.keys()) - set(stage.__dict__.keys()))) > 0:
      raise Exception(f"Attributes from parameter {stage_dict} does not match with class attributes. \
        Unknown attribute(s) are: {list(set(stage_dict.keys()) - set(stage.__dict__.keys()))}")



  def __eq__(self, other):
    print('equals 2 stages')
 #   other.next_stages !!! ist das Problem
    if (self.description, self.host, self.base_dir, self.build_dir, self.next_stages.get_all_names(), self.clear_files, self.processing_steps, self.lib_replacement_necessary, self.lib_mapping, self.status, self.create_time, self.update_time) != \
       (other.description, other.host, other.base_dir, self.build_dir, other.next_stages.get_all_names(), other.clear_files, other.processing_steps, other.lib_replacement_necessary, other.lib_mapping, other.status, other.create_time, other.update_time):
      return False

    return True





class Stage_List_list(list):

    def __init__(self, workflow:str=None, iterable=None):

      # This is only not to change the original parameter
      iterable2 = []
      if (iterable is not None and workflow is None) or (iterable is None and workflow is not None):
        raise Exception(f'Missing parameter to get the list data: {iterable=}, {workflow=}')

      if iterable is not None and len(iterable) > 0 and workflow is not None:
        for i, s in enumerate(iterable):
          iterable2.append(s)
          if type(s) == str:
             iterable2[i] = Stage.get_stage(workflow, s)
          if type(s) == dict:
             iterable2[i] = Stage.get_stage_from_dict(workflow, s)
             
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
          if item.name == stage.name:
            logging.info(f"Stage {item.name} already exist with status '{stage.status}'. Status will be set to 'new'.")
            item.status = Cmd_Status.NEW
            return

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



    def get_dict(self) -> {}:
      list = []

      for s in self:
        list.append(s.get_dict())

      return list



    #@validate_arguments
    def get_stage(self, name: str) -> Stage:

      for s in self:
        if s.name == name:
          return s

      raise Exception(f"Stage {name} not found in list {self.get_all_names()}")
      return None


    #@validate_arguments
    def get_stage_list_by_status(self, status: Cmd_Status) -> []:

      stages = Stage_List_list()

      for s in self:
        if s.status == status:
          stages.append(s)

      return stages



    def get_open_stages(self) -> []:

      stages = Stage_List_list()

      for s in self:
        if s.status != Cmd_Status.FINISHED:
          stages.append(s)

      return stages



    def remove_stage(self, name: str) -> None:

      for i, o in enumerate(self):
        if o.name == name:
          del self[i]
          return

