from __future__ import annotations
import json
import logging

from etc import constants





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


  def __init__(self, name='', dict={}):

    self.name = name

    if len(dict) > 0:

      self.name = dict['name'].lower()
      
      if len(dict['step_2_script_mapping']) > 0:
        self.step_2_script_mapping = dict['step_2_script_mapping']

      return

    self.step_2_script_mapping = self.get_workflow_steps()



  def get_workflow_steps(self) -> {}:
    with open(constants.C_WORKFLOW, "r") as file:
      workflows_json = json.load(file)

    for wf in workflows_json:
      if self.name == wf['name']:
        return wf["step_2_script_mapping"]
    
    return constants.C_DEFAULT_STEP_2_CMD_MAPPING



  def get_scripts(self, step_name:str) -> str:

    for step in self.step_2_script_mapping:
      if step['step'] == step_name:
        return step['scripts']



  def get_dict(self) -> {}:
    return {
      'name' : self.name,
      'step_2_script_mapping' : self.step_2_script_mapping,
    }



  def __eq__(self, o):
    if self.name == o.name:
      return True
    return False