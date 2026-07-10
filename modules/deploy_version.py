
import datetime
import json
import logging

# from pydantic import validate_arguments

from modules import meta_file
from modules.db import app_sqlite
from modules.meta_file_status import Meta_file_status
import logging

# from operator import itemgetter
# from modules.permission_config import check_user_permission

class DeploymentExistException(Exception):
    pass

class StatusConflictException(Exception):
    pass


class Deploy_Version:

    @staticmethod
    def get_next_deploy_version(project:str, status : Meta_file_status) -> dict:
        """
        Determines the next deployment version number for a project and records it in the database.
        """
        logging.debug(f"Get next deploy version for {project=}")
        
        with app_sqlite.get_db_connection() as conn:
            cursor = conn.cursor()

            # Get the last version for the project
            cursor.execute("SELECT MAX(id) FROM deploy_versions WHERE project = ?", (project,))
            result = cursor.fetchone()
            last_version = result[0] if result and result[0] is not None else 0
            
            new_version = last_version + 1

            new_deployment = {
                'version': new_version,
                'status': status.value,
                'timestamp': str(datetime.datetime.now()),
                'commit': None  # Initially commit is unknown
            }
            
            details_json = json.dumps(new_deployment)
            
            cursor.execute(
                "INSERT INTO deploy_versions (project, version, details) VALUES (?, ?, ?)",
                (project, new_version, details_json)
            )
            last_id = cursor.lastrowid

            conn.commit()
            
            logging.info(f"Created next deploy version {new_version} for project {project}.")
        return {"version": new_version, "id": last_id}



    @staticmethod
    def get_deployments(project: str) -> dict:
        """
        Retrieves all deployments for a given project from the SQLite database.
        """
        logging.debug(f"Getting deployments for project: {project}")
        
        with app_sqlite.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                           SELECT 
                                dv.version as version, mf.*, mf.id as meta_file_id,
                                MAX(dv.version) OVER (partition by dv.project) as last_deploy_version,
                                wd.name as workflow_name, wd.default_project
                           FROM deploy_versions dv
                           inner join meta_files mf on dv.id = mf.deploy_version_id
                           left join workflow_definitions wd on mf.id = wd.meta_file_id
                           WHERE dv.project = ? ORDER BY dv.version DESC
                           """, (project,))
            rows = cursor.fetchall()

            if not rows:
                return {"versions": {"last_deploy_version": 0}, "deployments": []}

            deployments = []
            for row in rows:
                row = dict(row)
                deployments.append(row)
            last_version = 0
            if deployments:
                last_version = deployments[0]['last_deploy_version']

        return {
            "versions": {"last_deploy_version": last_version},
            "deployments": deployments
        }



    @staticmethod
    def validate_deployment(project:str, version : int, status : Meta_file_status, commit : str|None=None):

        versions_config = Deploy_Version.get_deployments(project)

        for d in versions_config['deployments']:

            if d['version'] == version:
                continue

            if (meta_file.Meta_file_status(d['status']) not in [meta_file.Meta_file_status.FAILED, meta_file.Meta_file_status.CANCELED] and
                commit is not None and d.get('commit') and commit == d['commit']):
                e = DeploymentExistException(f"Commit {commit} already exist in deployment {d}")
                logging.exception(e, stack_info=True)
                raise e

            if (d['version'] < version and
                status == meta_file.Meta_file_status.IN_PROCESS and 
                meta_file.Meta_file_status(d['status']) not in [meta_file.Meta_file_status.FINISHED, meta_file.Meta_file_status.CANCELED]):
                e = StatusConflictException(f"Because version {d['version']} is still in status '{d['status']}', version {version} can't be updated to status '{status.value}'")
                logging.exception(e, stack_info=True)
                raise e





    @staticmethod
    def update_deploy_status(project: str, version: int, status: Meta_file_status, commit: str):
        """
        Updates the status of a deployment version in the SQLite database.
        """
        logging.debug(f"Update deployment status: {version=}, {status=}, {commit=}")

        Deploy_Version.validate_deployment(project=project, version=version, status=status, commit=commit)

        with app_sqlite.get_db_connection() as conn:
            cursor = conn.cursor()

            # First, get the current details
            cursor.execute("SELECT details FROM deploy_versions WHERE project = ? AND version = ?", (project, version))
            row = cursor.fetchone()

            if row:
                details = json.loads(row['details'])
                details['status'] = status.value
                details['commit'] = commit
                details['timestamp'] = str(datetime.datetime.now())
                
                details_json = json.dumps(details)
                
                cursor.execute(
                    "UPDATE deploy_versions SET details = ? WHERE project = ? AND version = ?",
                    (details_json, project, version)
                )
                conn.commit()
                logging.info(f"Successfully updated status for deployment {version} of project {project}.")
            else:
                logging.error(f"Deployment version {version} for project {project} not found.")



    @staticmethod
    def get_deployment(project:str, version : int):
        """
        Retrieves a specific deployment by its version number from the SQLite database.
        """
        if isinstance(version, str):
            version = int(version)
            
        logging.debug(f"Get deployment {version=}, {project=}")
        
        with app_sqlite.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT details FROM deploy_versions WHERE project = ? AND version = ?", (project, version))
            row = cursor.fetchone()

            if row:
                return json.loads(row['details'])

        err = Exception(f"Couldn't find deployment version {version}: {project=}") 
        logging.exception(err, stack_info=True)
        raise err



    @staticmethod
    def get_deployment_by_commit(project:str, commit : str):
        """
        Retrieves a deployment by its commit hash from the SQLite database.
        """
        logging.debug(f"Get deployment by {commit=}, {project=}")
        
        if commit is None:
            logging.info(f"Commit is None, returning None for {project=}")
            return None
        
        with app_sqlite.get_db_connection() as conn:
            cursor = conn.cursor()
            # This is not efficient, but without full-text search or a dedicated column, it's the way to go with JSON blobs.
            cursor.execute("SELECT details FROM deploy_versions WHERE project = ?", (project,))
            rows = cursor.fetchall()

            for row in rows:
                details = json.loads(row['details'])
                if details.get('commit') == commit:
                    return details

        logging.info(f"Couldn't find deployment with commit {commit}: {project=}")
        return None

