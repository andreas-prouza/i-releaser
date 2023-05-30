from __future__ import annotations
import json
import logging

from etc import constants
from modules import stages, workflow, meta_file





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



  def check_stage_run(self, stage:str=None):
    

    if stage is None:
       raise Exception('No stage was given to check')

    version_file = constants.C_DEPLOY_VERSION.format(project=self.project)

    with open(version_file, "r") as file:
        versions_config = json.load(file)

    deployments = versions_config['deployments']
    deployments_sorted = sorted(deployments, key=lambda x: x['version'])

    for deployment in deployments_sorted:
       if deployment['status'] == meta_file.Meta_file_status.FINISHED:
          continue
       if deployment['version'] < self.version:
          mf = meta_file.Meta_File.load_json_file(deployment['meta_file'])
          self.is_stage_open(mf, stage)
          

    version = versions_config['versions']['last_deploy_version'] + 1
    versions_config['versions']['last_deploy_version'] = version




  def is_stage_open(self, meta_file_obj:meta_file.Meta_File, stage:str):
    
    if stage in meta_file_obj.current_stages.get_all_names():
       return True
    
#    for next_stage in meta_file_obj.current_stages:
#       next_stage.next_stages[]
