from __future__ import annotations
import os
import datetime
import json
import logging

from pydantic import validate_arguments

from etc import constants
from modules import meta_file
from operator import itemgetter


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



    def update_deploy_status(project:str, version : int, status : meta_file.Meta_file_status, meta_file_name : str):

      logging.debug(f"Update meta file status: {version=}, {status=}, {meta_file_name}")
      version_file = constants.C_DEPLOY_VERSION.format(project=project)

      logging.debug(f"Load {version_file}")

      with open(version_file, "r") as file:
          versions_config = json.load(file)

      deployments = versions_config['deployments']
      deployments = sorted(deployments, key=itemgetter('version')) 

      for d in deployments:
        if d['version'] == version:
          logging.debug(f"Found {d}")
          d['status'] = status.value
          d['meta_file'] = meta_file_name
          d['timestamp'] = str(datetime.datetime.now())
          break

        if (status == meta_file.Meta_file_status.IN_PROCESS and 
            meta_file.Meta_file_status(d['status']) not in [meta_file.Meta_file_status.FINISHED, meta_file.Meta_file_status.FAILED]):
          e = Exception(f"Because version {d['version']} is still in status {d['status']}, version {version} can't be updated to status {status}")
          logging.exception(e)
          raise e

      logging.debug(f"Write {version_file}")

      with open(version_file, 'w') as file:
          json.dump(versions_config, file, default=str, indent=2)



    @validate_arguments
    def get_deployment(project:str, version : int):

      logging.debug(f"Get deployment {version=}, {project=}") 
      logging.debug(f"{constants.C_DEPLOY_VERSION=}") 
      version_file = constants.C_DEPLOY_VERSION.format(project=project)
      logging.debug(f"{os.path.abspath(version_file)}")

      with open(version_file, "r") as file:
          versions_config = json.load(file)

      deployments = versions_config['deployments']


      for d in reversed(deployments):
        if d['version'] == version:
          return d

      err = Exception(f"Couldn't find deployment version {version}: {project=}") 
      logging.error(err)
      raise Exception(f"Couldn't find deployment version {version}: {project=}") 

