import json

from etc import constants
from modules import files, workflow, meta_file





class Deploy_Checks:
  """Checks if a deployment is valid to run
  Attributes
  ----------
  ----------
  """


  def __init__(self, workflow: workflow.Workflow, project:str=None, version:int=None):

    self.workflow = workflow
    self.project = project
    self.version = version
    self.deploy_versions = []




  def is_stage_open(self, meta_file_obj:meta_file.Meta_File, stage:str):
    
    if stage in meta_file_obj.open_stages.get_all_names():
       return True
    
#    for next_stage in meta_file_obj.open_stages:
#       next_stage.next_stages[]
