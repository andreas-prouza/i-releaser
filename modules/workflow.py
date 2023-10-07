from __future__ import annotations
import json, os
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
    self.default_project = None
    self.step_2_script_mapping = None
    self.stages = None

    logging.debug(f"{name=}, {dict=}")

    if len(dict) > 0:

      self.name = dict['name'].lower()
      
      if 'step_2_script_mapping' in dict:
        self.step_2_script_mapping = dict['step_2_script_mapping']

      if 'default_project' in dict:
        self.default_project = dict['default_project']

      return

    self.load_workflow_data()
    #self.step_2_script_mapping = self.get_workflow_steps_mapping()



  def load_workflow_data(self) -> None:

    logging.debug(f"Workflow file: {os.path.abspath(constants.C_WORKFLOW)}")
    with open(constants.C_WORKFLOW, "r") as file:
      workflows_json = json.load(file)

    for wf in workflows_json:

      if self.name == wf['name']:

        Workflow.validate_workflow(wf)
        if 'step_2_script_mapping' in wf:
          self.step_2_script_mapping = wf["step_2_script_mapping"]
        if 'default_project' in wf:
          self.default_project = wf["default_project"]

        self.stages = wf['stages']

        return
    
    raise Exception(f"No workflow found with name '{self.name}'")



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




  def get_workflow_steps_mapping(self) -> {}:
    with open(constants.C_WORKFLOW, "r") as file:
      workflows_json = json.load(file)

    for wf in workflows_json:
      if self.name == wf['name']:
        Workflow.validate_workflow(wf)
        return wf["step_2_script_mapping"]
    
    return constants.C_DEFAULT_STEP_2_CMD_MAPPING



  def get_workflow_stage(workflow_name: str, stage_name: str) -> {}:

    logging.debug(f'Get stage for {workflow_name=}, {stage_name=}, {constants.C_WORKFLOW=}')
    with open(constants.C_WORKFLOW, "r") as file:
      workflows_json = json.load(file)

    for wf in workflows_json:
      if workflow_name == wf['name']:

        Workflow.validate_workflow(wf)

        for stage in wf["stages"]:
          if stage['name'] == stage_name:
            logging.debug(f'Found {stage=}')
            return stage
    
    logging.warning(f"No stage found in workflows!")
    return None



  def validate_workflow(workflow_dict: {}) -> None:

    if 'name' not in workflow_dict.keys():
      raise Exception(f"No workflow name is defined!")

    if 'stages' not in workflow_dict.keys() or len(workflow_dict['stages']) == 0:
      raise Exception(f"No stage definition for workflow {workflow_dict['name']}!")

    stages.Stage_List_list.validate_items(workflow_dict['stages'])

    for key in workflow_dict.keys():
      if key not in ['name', 'step_2_script_mapping', 'stages', 'default_project']:
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
      'object_commands': self.object_commands,
      'default_project': self.default_project
    }



  def __eq__(self, o):
    if self.name == o.name and self.step_2_script_mapping == o.step_2_script_mapping:
      return True
    return False