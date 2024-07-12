from __future__ import annotations
import json, os
import logging

from etc import constants
from modules import stages, deploy_action


class MissingProcessingStepMappingException(Exception):
  pass

class WorkflowNotFoundException(Exception):
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

  name: str
  

  def __init__(self, name=None, dict={}):

    self.name = name
    self.object_commands = []
    self.default_project = None
    self.step_action = None
    self.stages = None

    logging.debug(f"{name=}, {dict=}")

    if len(dict) > 0:

      self.name = dict['name'].lower()
      
      if 'step_action' in dict:
        self.step_action = dict['step_action']

      if 'default_project' in dict:
        self.default_project = dict['default_project']

      if 'stages' in dict:
        self.stages = dict['stages']

      return

    self.load_workflow_data()
    #self.step_action = self.get_workflow_steps_mapping()



  def load_workflow_data(self) -> None:

    logging.debug(f"Workflow file: {os.path.abspath(constants.C_WORKFLOW)}")
    with open(constants.C_WORKFLOW, "r") as file:
      workflows_json = json.load(file)

    for wf in workflows_json:

      if self.name == wf['name']:

        Workflow.validate_workflow(wf)
        if 'step_action' in wf:
          self.step_action = wf["step_action"]
        if 'default_project' in wf:
          self.default_project = wf["default_project"]

        self.stages = wf['stages']

        return
    
    raise WorkflowNotFoundException(f"No workflow found with name '{self.name}'")



  def get_default_step_mapping() -> {}:

    with open(constants.C_DEFAULT_STEP_ACTION, "r") as file:
      step_mapping_json = json.load(file)
      return step_mapping_json
    
    return None



  def get_all_projects() -> []:
    
    projects=[]

    with open(constants.C_WORKFLOW, "r") as file:
      workflows_json = json.load(file)

    for wf in workflows_json:
      if wf['default_project'] not in projects:
        projects.append(wf['default_project'])

    return projects


  def get_all_workflow_json():
    
    with open(constants.C_WORKFLOW, "r") as file:
      workflows_json = json.load(file)

    return workflows_json



  def get_stage(self, stage_name:str) -> {}:
    """
    Retrieves stage dict from workflow.json

    Args:
        stage_name (str): Name of stage
    Returns:
        stage (dict): Stage as dictionary
    """
    for stage in self.stages:
      if stage['name'] == stage_name:
        logging.debug(f'Found stage in workflow: {stage=}')
        return stage



  def get_workflow_steps_mapping(workflow_dict: {}) -> []:
    """
    Get steps mapping list of the current workflow + the global constants definition

    Returns:
        mapping_lsit (list): List of mappings
    """

    step_mapping = Workflow.get_default_step_mapping()

    if 'step_action' in workflow_dict.keys():
      logging.debug(f'len {len(step_mapping)=}, {len(workflow_dict["step_action"])=}')
      merged_list = {x['processing_step']:x for x in step_mapping + workflow_dict["step_action"]}.values()
      logging.debug(f"{merged_list=}")
      return merged_list
    
    return step_mapping




  def validate_workflow(workflow_dict: {}) -> None:

    if 'name' not in workflow_dict.keys():
      raise Exception(f"No workflow name is defined!")

    if 'default_project' not in workflow_dict.keys():
      raise Exception(f"No default_project name is defined!")

    if 'stages' not in workflow_dict.keys() or len(workflow_dict['stages']) == 0:
      raise Exception(f"No stage definition for workflow {workflow_dict['name']}!")

    stages.Stage_List_list.validate_items(workflow_dict['stages'])

    for key in workflow_dict.keys():
      if key not in ['name', 'step_action', 'stages', 'default_project']:
        raise Exception(f"Workflow attribute '{key}' is invalid!")
    
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
          if key not in ['processing_step', 'environment', 'execute', 'check_error']:
            raise Exception(f"Script-Mapping attribute '{key}' is invalid for workflow {workflow_dict['name']}!")



  def get_scripts(self, step_name:str) -> str:

    for step in self.step_action:
      if step['step'] == step_name:
        return step['script']



  def get_dict(self) -> {}:
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