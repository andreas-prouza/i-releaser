from __future__ import annotations
import json
import logging

from etc import constants
from modules import stages





class Workflow:
  """Stored information of an workflow
  Attributes
  ----------
  name : str
      Name of the workflow
  step_2_script_mapping : list
      A list of steps and the related scripts to run fo that step
  stages : list
      A list of stages for this workflow
  ----------
  """

  name: str
  

  def __init__(self, name='', dict={}):

    self.name = name
    self.object_commands = []

    if len(dict) > 0:

      self.name = dict['name'].lower()
      self.object_commands = dict['object_commands']
      self.step_2_script_mapping = dict['step_2_script_mapping']

      return

    self.step_2_script_mapping = self.get_workflow_steps_mapping()



  def get_workflow_steps_mapping(self) -> {}:
    with open(constants.C_WORKFLOW, "r") as file:
      workflows_json = json.load(file)


    for wf in workflows_json:
      if self.name == wf['name']:
        Workflow.validate_workflow(wf)
        return wf["step_2_script_mapping"]
    
    return constants.C_DEFAULT_STEP_2_CMD_MAPPING



  def get_workflow_stage(workflow_name: str, stage_name: str) -> {}:

    with open(constants.C_WORKFLOW, "r") as file:
      workflows_json = json.load(file)


    for wf in workflows_json:
      if workflow_name == wf['name']:

        Workflow.validate_workflow(wf)

        for stage in wf["stages"]:
          if stage['name'] == stage_name:
            return stage
    
    return None


  def validate_workflow(workflow_dict: {}) -> None:

    if 'name' not in workflow_dict.keys():
      raise Exception(f"No workflow name is defined!")

    if 'stages' not in workflow_dict.keys() or len(workflow_dict['stages']) == 0:
      raise Exception(f"No stage definition for workflow {workflow_dict['name']}!")

    stages.Stage_List_list.validate_items(workflow_dict['stages'])

    for key in workflow_dict.keys():
      if key not in ['name', 'step_2_script_mapping', 'stages']:
        raise Exception(f"Workflow attribute '{key}' is invalid!")
    
    if 'step_2_script_mapping' in workflow_dict.keys():
      script_mappings = workflow_dict['step_2_script_mapping']
      for mapping in script_mappings:
        for key in mapping.keys():
          if key not in ['processing_step', 'environment', 'execute', 'check_error']:
            raise Exception(f"Script-Mapping attribute '{key}' is invalid for workflow {workflow_dict['name']}!")



  def get_scripts(self, step_name:str) -> str:

    for step in self.step_2_script_mapping:
      if step['step'] == step_name:
        return step['script']



  def get_dict(self) -> {}:
    return {
      'name': self.name,
      'step_2_script_mapping': self.step_2_script_mapping,
      'object_commands': self.object_commands
    }



  def __eq__(self, o):
    if self.name == o.name:
      return True
    return False