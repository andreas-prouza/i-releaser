from __future__ import annotations
import os
import datetime
import json
import logging

# from pydantic import validate_arguments

from etc import constants
from modules import meta_file
from operator import itemgetter

class DeploymentExistException(Exception):
    pass

class StatusConflictException(Exception):
    pass


class Deploy_Version:

    def get_next_deploy_version(project:str, status : meta_file.Meta_file_status) -> int:

      version_file = constants.C_DEPLOY_VERSION.format(project=project)

      versions_config = Deploy_Version.get_deployments(version_file)

      if versions_config == None:
        versions_config = {
                            "versions": {
                              "last_deploy_version": 0
                            },
                            "deployments": [
                            ]
                          }


      version = versions_config['versions']['last_deploy_version'] + 1
      versions_config['versions']['last_deploy_version'] = version

      if 'deployments' not in versions_config:
        versions_config['deployments'] = []

      versions_config['deployments'].append({
        'version': version,
        'status': status.value,
        'timestamp': str(datetime.datetime.now())
      })

      versions_config['deployments'] = sorted(versions_config['deployments'], key=lambda d: d['version'], reverse=True)

      with open(version_file, 'w') as file:
          json.dump(versions_config, file, default=str, indent=2)

      return version



    def get_deployments(version_file):

      logging.debug(os.path.abspath(version_file))
      if os.path.isfile(version_file):
        with open(version_file, "r") as file:
            return json.load(file)
        
      return None




    def validate_deployment(project:str, version : int, status : meta_file.Meta_file_status, meta_file_name : str, commit : str):

      versions_config = Deploy_Version.get_deployments(Deploy_Version.get_deployment_file(project=project))

      for d in versions_config['deployments']:

        if d['version'] == version:
          continue

        if (meta_file.Meta_file_status(d['status']) not in [meta_file.Meta_file_status.FAILED, meta_file.Meta_file_status.CANCELED] and
            commit is not None and commit == d['commit']):
          e = DeploymentExistException(f"Commit {commit} already exist in deployment {d}")
          logging.exception(e, stack_info=True)
          raise e

        if (d['version'] < version and
            status == meta_file.Meta_file_status.IN_PROCESS and 
            meta_file.Meta_file_status(d['status']) not in [meta_file.Meta_file_status.FINISHED, meta_file.Meta_file_status.CANCELED]):
          e = StatusConflictException(f"Because version {d['version']} is still in status '{d['status']}', version {version} can't be updated to status '{status.value}'")
          logging.exception(e, stack_info=True)
          raise e





    def get_deployment_file(project:str):
      return constants.C_DEPLOY_VERSION.format(project=project)




    def update_deploy_status(project:str, version : int, status : meta_file.Meta_file_status, meta_file_name : str, commit : str):

      logging.debug(f"Update meta file status: {version=}, {status=}, {meta_file_name}, {commit}")
      version_file = Deploy_Version.get_deployment_file(project=project)

      Deploy_Version.validate_deployment(project=project, version=version, status=status, meta_file_name=meta_file_name, commit=commit)

      logging.debug(f"Load {version_file}")

      versions_config = Deploy_Version.get_deployments(version_file)

      deployments = versions_config['deployments']
      deployments = sorted(deployments, key=itemgetter('version')) 

      for d in deployments:
        if d['version'] == version:
          logging.debug(f"Found {d}")
          d['status'] = status.value
          d['meta_file'] = meta_file_name
          d['commit'] = commit
          d['timestamp'] = str(datetime.datetime.now())
          break

      logging.debug(f"Write {version_file}")

      with open(version_file, 'w') as file:
          json.dump(versions_config, file, default=str, indent=2)



    #@validate_arguments
    def get_deployment(project:str, version : int):

      if type(version) == str:
        version = int(version)
        
      logging.debug(f"Get deployment {version=}, {project=}") 
      version_file = constants.C_DEPLOY_VERSION.format(project=project)
      logging.debug(f"{version_file=}") 
      deployments = Deploy_Version.get_deployments(version_file)['deployments']

      for d in reversed(deployments):
        if d['version'] == version:
          return d

      logging.error(deployments)

      err = Exception(f"Couldn't find deployment version {version}: {project=}") 
      logging.exception(err, stack_info=True)
      raise Exception(f"Couldn't find deployment version {version}: {project=}") 



    def get_deployment_by_commit(project:str, commit : str):

      logging.debug(f"Get deployment {commit=}, {project=}") 
      version_file = constants.C_DEPLOY_VERSION.format(project=project)
      deployments = Deploy_Version.get_deployments(version_file)['deployments']

      for d in reversed(deployments):
        if d.get('commit', None) is not None and d['commit'] == commit:
          return d

      logging.info(f"Couldn't find deployment with commit {commit}: {project=}")
      return None

