import sqlite3
import os
import logging
import json
import glob
from etc import constants
import glob

DB_FILE = os.path.abspath(constants.C_APP_DB_FILE)



def get_db_connection(db_path=DB_FILE):
    """Establishes a connection to the SQLite database."""

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn




def create_tables(db_path=DB_FILE):
    """Creates all necessary tables in the SQLite database if they don't exist."""

    db_dir = os.path.dirname(os.path.abspath(db_path))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    with get_db_connection(db_path) as conn:
        c = conn.cursor()


        c.execute("""
            CREATE TABLE IF NOT EXISTS app_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT NOT NULL,
                data TEXT NOT NULL,
                start_time timestamp default CURRENT_TIMESTAMP
            );
            """)


        c.execute("""
            CREATE TABLE IF NOT EXISTS deploy_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                version INTEGER NOT NULL,
                details TEXT, -- Storing the deployment details as a JSON string
                UNIQUE(project, version)
            );
            """)


        # Main meta_files table
        c.execute('''
            CREATE TABLE IF NOT EXISTS meta_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT,
                deploy_version_id INTEGER,
                meta_dir TEXT,
                commit_hash TEXT,
                release_branch TEXT,
                create_time timestamp,
                update_time timestamp,
                status TEXT,
                object_list TEXT,
                main_lib TEXT,
                remote_lib TEXT,
                backup_lib TEXT,
                custom_data TEXT,
                FOREIGN KEY (deploy_version_id) REFERENCES deploy_versions (id)
            )
        ''')

        # Workflow definition table
        c.execute('''
            CREATE TABLE IF NOT EXISTS workflow_definitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meta_file_id INTEGER,
                name TEXT,
                default_project TEXT,
                definition TEXT,
                FOREIGN KEY (meta_file_id) REFERENCES meta_files (id)
            )
        ''')

        # Processing users table
        c.execute('''
            CREATE TABLE IF NOT EXISTS processing_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meta_file_id INTEGER,
                action TEXT,
                user TEXT,
                timestamp TEXT,
                stage TEXT,
                details TEXT,
                FOREIGN KEY (meta_file_id) REFERENCES meta_files (id)
            )
        ''')

        # Run history table
        c.execute('''
            CREATE TABLE IF NOT EXISTS run_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meta_file_id INTEGER,
                create_time timestamp,
                log TEXT,
                FOREIGN KEY (meta_file_id) REFERENCES meta_files (id)
            )
        ''')

        # Stages table
        c.execute('''
            CREATE TABLE IF NOT EXISTS stages (
                id INTEGER PRIMARY KEY,
                meta_file_id INTEGER,
                name TEXT,
                description TEXT,
                host TEXT,
                base_dir TEXT,
                remote_dir TEXT,
                build_dir TEXT,
                next_stages TEXT,
                next_stage_ids TEXT,
                after_stages_finished TEXT,
                clear_files BOOLEAN,
                processing_steps TEXT,
                execute_remote BOOLEAN,
                lib_replacement_necessary BOOLEAN,
                lib_mapping TEXT,
                status TEXT,
                create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (meta_file_id) REFERENCES meta_files (id)
            )
        ''')
        
        # Deploy objects table
        c.execute('''
            CREATE TABLE IF NOT EXISTS deploy_objects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meta_file_id INTEGER,
                level INTEGER,
                prod_lib TEXT,
                lib TEXT,
                name TEXT,
                type TEXT,
                attribute TEXT,
                deploy_status TEXT,
                ready BOOLEAN,
                FOREIGN KEY (meta_file_id) REFERENCES meta_files (id)
            )
        ''')

        # Actions table
        c.execute('''
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY,
                stage_id INTEGER,
                deploy_object_id INTEGER,
                action_id INTEGER,
                sequence INTEGER,
                cmd TEXT,
                status TEXT,
                processing_step TEXT,
                environment TEXT,
                run_in_new_job BOOLEAN,
                execute_remote BOOLEAN,
                check_error BOOLEAN,
                FOREIGN KEY (stage_id) REFERENCES stages (id),
                FOREIGN KEY (deploy_object_id) REFERENCES deploy_objects (id),
                FOREIGN KEY (action_id) REFERENCES actions (id)
            )
        ''')

        # Action run history table
        c.execute('''
            CREATE TABLE IF NOT EXISTS action_run_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_id INTEGER,
                create_time TEXT,
                status TEXT,
                stdout TEXT,
                stderr TEXT,
                FOREIGN KEY (action_id) REFERENCES actions (id)
            )
        ''')

        conn.commit()
    logging.info("SQLite tables for meta files created successfully.")


if __name__ == '__main__':
    # This allows the script to be run directly to initialize the database
    print("Initializing meta file SQLite database...")
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        print(f"Removed existing database file: {DB_FILE}")
    create_tables()
    print("Database and tables created.")
