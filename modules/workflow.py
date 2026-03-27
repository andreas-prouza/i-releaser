from __future__ import annotations
import json, os
import logging
from typing import List

from etc import constants
from modules import stages, deploy_action
import glob


class MissingProcessingStepMappingException(Exception):
  pass

class WorkflowNotFoundException(Exception):
  pass

class StageRecursionException(Exception):
  pass



class Workflow:
  """Stored information of an workflow
  Attributes
  ----------
  name : str
      Name of the workflow
  step_action : list
      A list of steps and the related scripts to run fo that step
  stages : list
      A list of stages for this workflow
  ----------
  """

  name: str|None
  

  def __init__(self, name: str|None=None, dict: dict|None={}):

    self.name = name.lower() if name else None
    self.object_commands = []
    self.default_project = None
    self.step_action = None
    self.stages = None

    logging.debug(f"{name=}, {dict=}")

    if dict is not None and len(dict) > 0:

      self.name = dict['name'].lower()
      
      if 'step_action' in dict:
        self.step_action = dict['step_action']

      if 'default_project' in dict:
        self.default_project = dict['default_project']

      if 'stages' in dict:
        self.stages = dict['stages']

      logging.debug(f"Workflow created from dict: {self.get_dict()}")

      return

    logging.debug(f"Dict is None: {dict=} {name=}")
    self.load_workflow_data()
    logging.debug(f"Workflow loaded: {self.get_dict()}")
    #self.step_action = self.get_workflow_steps_mapping()



  def load_workflow_data(self) -> None:

    if not self.name:
      raise Exception(f"No workflow name provided for loading workflow data!")
    wf = self.get_workflow_by_name(self.name)
    self.__dict__.update(wf.__dict__)
    logging.debug(f"Workflow data loaded for workflow {self.get_dict()}!")



  @staticmethod
  def get_default_step_mapping() -> List[dict]|None:

    with open(constants.C_DEFAULT_STEP_ACTION, "r") as file:
      step_mapping_json = json.load(file)
      return step_mapping_json
    
    return None


  @staticmethod
  def get_workflow_by_name(workflow_name:str) -> Workflow:

    workflows_json = Workflow.get_all_workflows_json()

    for wf in workflows_json:

      if workflow_name == wf['name'].lower():
        return Workflow(dict=wf)
    
    raise WorkflowNotFoundException(f"No workflow found with name '{workflow_name}'")



  @staticmethod
  def get_all_workflows_from_old_workflow_json() -> List[dict]:

    if not os.path.isfile(constants.C_WORKFLOW):
      logging.info(f"No old workflow file found at {constants.C_WORKFLOW}! Very good!")
      return []
    
    import warnings
    warnings.warn(f"Use of old workflow file: {os.path.abspath(constants.C_WORKFLOW)}. Migrate to single etc/workflows/*.json file for each workflow!", DeprecationWarning, stacklevel=2)
    logging.warning(f"Use of old workflow file: {os.path.abspath(constants.C_WORKFLOW)}. Migrate to single etc/workflows/*.json file for each workflow!")

    with open(constants.C_WORKFLOW, "r") as file:
      workflows_json = json.load(file)

    return workflows_json




  @staticmethod
  def get_all_projects() -> List[str]:
    
    projects=[]

    workflows_json = Workflow.get_all_workflows_json()

    for wf in workflows_json:
      if wf['default_project'] not in projects:
        projects.append(wf['default_project'])

    return projects



  @staticmethod
  def get_all_workflows_json() -> List[dict]:

    workflow_files = glob.glob(os.path.join(constants.C_WORKFLOWS_DIR, "*.json"))
    workflows_json = []

    for wf_file in workflow_files:

      try:

        with open(wf_file, "r") as file:

          json_data = json.load(file)

          if not isinstance(json_data, dict):
              raise Exception(f"Workflow file contains a {type(json_data)} instead of dict.")

          Workflow.validate_workflow(json_data, wf_file)

          workflows_json.append(json_data)

      except Exception as e:

        error = Exception(f"Error loading workflow file {wf_file}: {e}")
        logging.error(error)
        raise error
    
    workflows_json += Workflow.get_all_workflows_from_old_workflow_json()

    return workflows_json



  def get_stage(self, stage_name:str) -> dict:
    """
    Retrieves stage dict from workflow.json

    Args:
        stage_name (str): Name of stage
    Returns:
        stage (dict): Stage as dictionary
    """
    if not self.stages:
      logging.info(f"Workflow: {self.get_dict()}")
      error = Exception(f"No stages defined for workflow {self.name}!")
      logging.exception(error, stack_info=True)
      raise error
    
    for stage in self.stages:
      if stage['name'] == stage_name:
        logging.debug(f'Found stage in workflow: {stage=}')
        return stage
      
    error = Exception(f"No stage found for {stage_name}!")
    logging.exception(error, stack_info=True)
    raise error



  @staticmethod
  def get_workflow_steps_mapping(workflow_dict: dict) -> List[dict]:
    """
    Get steps mapping list of the current workflow + the global constants definition

    Returns:
        mapping_lsit (list): List of mappings
    """

    step_mapping: List[dict] = Workflow.get_default_step_mapping() or []

    if 'step_action' in workflow_dict.keys() and workflow_dict['step_action'] is not None:
      logging.debug(f'len {len(step_mapping)=}, {len(workflow_dict["step_action"])=}')
      merged_list = {x['processing_step']:x for x in step_mapping + workflow_dict["step_action"]}.values()
      logging.debug(f"{merged_list=}")
      return list(merged_list)
    
    return step_mapping




  @staticmethod
  def validate_workflow(workflow_dict: dict, wf_file: str) -> None:

    if 'name' not in workflow_dict.keys():
      raise Exception(f"No workflow name is defined in file {wf_file}!")

    if 'default_project' not in workflow_dict.keys():
      raise Exception(f"No default_project name is defined in file {wf_file}!")

    if 'stages' not in workflow_dict.keys() or len(workflow_dict['stages']) == 0:
      raise Exception(f"No stage definition for workflow {workflow_dict['name']} in file {wf_file}!")

    stages.Stage_List_list.validate_items(workflow_dict['stages'])

    for key in workflow_dict.keys():
      if key not in ['name', 'step_action', 'stages', 'default_project']:
        raise Exception(f"Workflow attribute '{key}' is invalid in file {wf_file}!")
    
    #######################################

    steps_mapping = Workflow.get_workflow_steps_mapping(workflow_dict=workflow_dict)
    for stage in workflow_dict['stages']:
      
      if 'processing_steps' not in stage.keys():
        continue

      for ps in stage['processing_steps']:
        found = False
        for sm in steps_mapping:
          if ps == sm['processing_step']:
            found = True
            break
        if not found:
          raise MissingProcessingStepMappingException(f"No process mapping found for step {ps} in stage {stage['name']}")

    if 'step_action' in workflow_dict.keys():
      script_mappings = workflow_dict['step_action']
      for mapping in script_mappings:
        for key in mapping.keys():
          if key not in ['processing_step', 'environment', 'execute', 'check_error', 'execute_remote']:
            raise Exception(f"Script-Mapping attribute '{key}' is invalid for workflow {workflow_dict['name']} in file {wf_file}!")

    ########################################

    Workflow.check_worfklow_loop(workflow_dict['stages'], wf_file=wf_file)




  @staticmethod
  def check_worfklow_loop(workflow_stages: List[dict], start_stage :str='START', counter :int=1, wf_file: str='') -> None:

    if counter >= 200:
      raise(StageRecursionException(f'Infinite loop ({counter}) in next_stage configuration: {workflow_stages=} in file {wf_file}'))

    for stage in workflow_stages:
      if stage['name'] == start_stage:
        for next_stage in stage.get('next_stages', []):
          counter += 1
          Workflow.check_worfklow_loop(
              workflow_stages=workflow_stages, 
              start_stage=next_stage, 
              counter=counter,
              wf_file=wf_file)






  def get_scripts(self, step_name:str) -> str|None:

    if not self.step_action:
      return None

    for step in self.step_action:
      if step['step'] == step_name:
        return step['script']

    return None


  def get_dict(self) -> dict:
    return {
      'name': self.name,
      'step_action': self.step_action,
      'object_commands': self.object_commands,
      'default_project': self.default_project,
      'stages': self.stages
    }



  def __eq__(self, o):
    if self.name == o.name and self.step_action == o.step_action:
      return True
    return False