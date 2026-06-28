import sqlite3
import os
import logging
import json
import glob
from etc import constants
import glob
from modules.db import app_sqlite


def migrate_from_json():
    """
    Migrates data from all deploy_version_*.json files into the SQLite database.
    Skips projects that already have entries in the database.
    """
    logging.info("Starting migration of deploy_version JSON files to SQLite...")
    conn = get_db_connection()
    cursor = conn.cursor()

    search_pattern = os.path.join(constants.C_LOCAL_BASE_DIR, "etc", "deploy_version_*.json")
    
    for file_path in glob.glob(search_pattern):
        try:
            project = os.path.basename(file_path).replace('deploy_version_', '').replace('.json', '')
            
            # Check if the project already exists in the table
            cursor.execute("SELECT 1 FROM deploy_versions WHERE project = ? LIMIT 1", (project,))
            if cursor.fetchone():
                logging.info(f"Project '{project}' already exists in the database. Skipping migration from {file_path}.")
                continue

            # If project doesn't exist, proceed with migration
            logging.info(f"Migrating data for project '{project}' from {file_path}...")
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            deployments = data.get('deployments', [])
            for deployment_details in deployments:
                version = deployment_details.get('version')
                if version is not None:
                    details_json = json.dumps(deployment_details)
                    cursor.execute(
                        "INSERT INTO deploy_versions (project, version, details) VALUES (?, ?, ?)",
                        (project, str(version), details_json)
                    )
            conn.commit()
            logging.info(f"Successfully migrated project '{project}'.")

        except (json.JSONDecodeError, sqlite3.Error) as e:
            logging.error(f"Failed to process or migrate file {file_path}: {e}", exc_info=True)
            conn.rollback()
            raise e

    conn.close()
    logging.info("Deploy version JSON migration to SQLite complete.")

