from __future__ import annotations
import datetime
import json
import logging

from etc import constants
from modules import meta_file


class Deploy_Version:

    def get_next_deploy_version(status : meta_file.Meta_file_status) -> int:

        with open(constants.C_DEPLOY_VERSION, "r") as file:
            versions_config = json.load(file)

        version = versions_config['versions']['last_deploy_version'] + 1
        versions_config['versions']['last_deploy_version'] = version

        if 'deployments' not in versions_config:
          versions_config['deployments'] = []

        versions_config['deployments'].append({
          'version': version,
          'status': status,
          'timestamp': str(datetime.datetime.utcnow())
        })

        versions_config['deployments'] = sorted(versions_config['deployments'], key=lambda d: d['version'], reverse=True)

        with open(constants.C_DEPLOY_VERSION, 'w') as file:
            json.dump(versions_config, file, indent=2)

        return version



    def update_deploy_status(version : int, status : meta_file.Meta_file_status, meta_file_name : str):

        logging.debug(f"Update meta file status: {version=}, {status=}, {meta_file_name}")

        with open(constants.C_DEPLOY_VERSION, "r") as file:
            versions_config = json.load(file)

        deployments = versions_config['deployments']

        for d in reversed(deployments):
          if d['version'] == version:
            d['status'] = status
            d['meta_file'] = meta_file_name
            d['timestamp'] = str(datetime.datetime.utcnow())
            break

          if (status == meta_file.Meta_file_status.IN_PROCESS and 
              meta_file.Meta_file_status(d['status']) not in [meta_file.Meta_file_status.FINISHED, meta_file.Meta_file_status.FAILED]):
            raise Exception(f"Because version {d['version']} is still in status {status}, version {version} can't be updated to status {status}")

        with open(constants.C_DEPLOY_VERSION, 'w') as file:
            json.dump(versions_config, file, indent=2)

