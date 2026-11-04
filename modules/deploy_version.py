
import datetime
import json
import logging

# from pydantic import validate_arguments

from modules import errors, meta_file
from modules.db import app_sqlite, meta_file_data
from modules.meta_file_status import Meta_file_status
import logging

# from operator import itemgetter
# from modules.permission_config import check_user_permission

class DeploymentExistException(errors.Conflict_Error):
    pass

class StatusConflictException(errors.Conflict_Error):
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

            # Reading the last version and adding the new one has to be atomic, also over multiple processes
            cursor.execute("BEGIN IMMEDIATE")

            # Get the last version for the project
            cursor.execute("SELECT MAX(version) FROM deploy_versions WHERE project = ?", (project,))
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
    def get_deployment_list(project: str) -> list[dict]:
        """Deployments of a project, newest first (the list of the Web API)"""

        with app_sqlite.get_db_connection() as conn:
            rows = conn.execute("""
                SELECT mf.id as meta_file_id, dv.version, mf.status, wd.name as workflow_name, mf.commit_hash as "commit", mf.create_time, mf.update_time
                  FROM deploy_versions dv
                  INNER JOIN meta_files mf ON dv.id = mf.deploy_version_id
                  LEFT JOIN workflow_definitions wd ON mf.id = wd.meta_file_id
                 WHERE dv.project = ?
                 ORDER BY dv.version DESC""", (project,)).fetchall()

        return [dict(row) for row in rows]



    @staticmethod
    def validate_deployment(project:str, version : int, status : Meta_file_status, commit : str|None=None, parallel_deployment_execution_allowed: bool=False):

        with app_sqlite.get_db_connection() as conn:

            if commit is not None and commit != '':
                row = conn.execute("""
                    SELECT dv.version FROM deploy_versions dv
                      INNER JOIN meta_files mf ON dv.id = mf.deploy_version_id
                     WHERE dv.project = ? AND dv.version <> ? AND mf.commit_hash = ? AND mf.status NOT IN (?, ?)
                     LIMIT 1""", (project, version, commit, Meta_file_status.FAILED.value, Meta_file_status.CANCELED.value)).fetchone()

                if row:
                    e = DeploymentExistException(f"Commit {commit} already exist in deployment {row['version']}")
                    logging.exception(e, stack_info=True)
                    raise e

            if not parallel_deployment_execution_allowed and status == Meta_file_status.IN_PROCESS:
                row = conn.execute("""
                    SELECT dv.version, mf.status FROM deploy_versions dv
                      INNER JOIN meta_files mf ON dv.id = mf.deploy_version_id
                     WHERE dv.project = ? AND dv.version < ? AND mf.status NOT IN (?, ?)
                     ORDER BY dv.version DESC
                     LIMIT 1""", (project, version, Meta_file_status.FINISHED.value, Meta_file_status.CANCELED.value)).fetchone()

                if row:
                    e = StatusConflictException(f"Because version {row['version']} is still in status '{row['status']}', version {version} can't be updated to status '{status.value}'")
                    logging.exception(e, stack_info=True)
                    raise e




    @staticmethod
    def update_deploy_status(project: str, version: int, status: Meta_file_status, commit: str, parallel_deployment_execution_allowed: bool=False):
        """
        Updates the status of a deployment version in the SQLite database.
        """
        logging.debug(f"Update deployment status: {version=}, {status=}, {commit=}")

        Deploy_Version.validate_deployment(project=project, version=version, status=status, commit=commit, parallel_deployment_execution_allowed=parallel_deployment_execution_allowed)

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
    def get_deployment(project:str, version : int) -> meta_file.Meta_File | None:
        """
        Retrieves a specific deployment by its version number from the SQLite database.
        """
        if isinstance(version, str):
            version = int(version)
            
        logging.debug(f"Get deployment {version=}, {project=}")
        
        with app_sqlite.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT m.id as meta_file_id, dv.details FROM deploy_versions dv LEFT JOIN meta_files m ON dv.id = m.deploy_version_id WHERE dv.project = ? AND dv.version = ?", (project, version))
            row = cursor.fetchone()

            if row:
                return meta_file_data.get_meta_file_by_id(row['meta_file_id'])

        raise errors.Not_Found_Error(f"Couldn't find deployment version {version}: {project=}")



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
            # Deployments which aren't canceled first: they are the ones which block the commit
            row = conn.execute("""
                SELECT dv.version, mf.status, mf.commit_hash as "commit" FROM deploy_versions dv
                  INNER JOIN meta_files mf ON dv.id = mf.deploy_version_id
                 WHERE dv.project = ? AND mf.commit_hash = ?
                 ORDER BY mf.status = ?, dv.version DESC
                 LIMIT 1""", (project, commit, Meta_file_status.CANCELED.value)).fetchone()

        if row:
            return dict(row)

        logging.info(f"Couldn't find deployment with commit {commit}: {project=}")
        return None
