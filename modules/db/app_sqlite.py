
import sqlite3
import os
import logging
from etc import constants
from modules.db import app_sqlite, compression
from modules.db import app_info_data


DB_FILE = os.path.abspath(constants.C_APP_DB_FILE)

# Columns which are used to select the data of a deployment
INDEXED_COLUMNS = [
    ('workflow_definitions', 'meta_file_id'),
    ('processing_users', 'meta_file_id'),
    ('run_history', 'meta_file_id'),
    ('stages', 'meta_file_id'),
    ('deploy_objects', 'meta_file_id'),
    ('actions', 'stage_id'),
    ('actions', 'deploy_object_id'),
    ('actions', 'action_id'),
    ('action_run_history', 'action_id'),
]



def get_db_connection(db_path=DB_FILE):
    """Establishes a connection to the SQLite database."""

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # In WAL mode, commits don't need to be synced to disk (only checkpoints do).
    # An OS crash may lose the latest commits, but never corrupts the database.
    if conn.execute("PRAGMA journal_mode").fetchone()[0] == 'wal':
        conn.execute("PRAGMA synchronous=NORMAL")

    return conn



def enable_wal(db_path=DB_FILE) -> bool:
    """
    Switches the database to WAL mode (persistent), so commits are cheaper and readers don't block writers.
    Keeps the rollback journal if that's not possible.
    """

    try:
        with get_db_connection(db_path) as conn:
            journal_mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
    except sqlite3.Error as e:
        journal_mode = str(e)

    if journal_mode != 'wal':
        logging.warning(f"Could not switch database to WAL mode ({journal_mode}). Rollback journal will be used.")
        return False

    return True




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
                parallel_deployment_execution_allowed BOOLEAN,
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
                run_immediate BOOLEAN,
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
                depends_on TEXT,
                properties TEXT,
                source TEXT,
                source_only BOOLEAN,
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
                cwd TEXT,
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

        for table, column in INDEXED_COLUMNS:
            c.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_{column} ON {table} ({column})")

        conn.commit()
    logging.info("SQLite tables for meta files created successfully.")

    enable_wal(db_path)





def check_updates():

    app_info: dict | None = app_info_data.get_app_info()
    if app_info is None:
        return

    last_version = app_info.get("version", "0.0.0")
    logging.info(f"Last app version in database: {last_version}")

    if last_version == '2.0.0':
        from modules.db.updates import v_2_0_1
        v_2_0_1.add_compression()
        last_version = '2.0.1'

    if last_version == '2.0.1':
        from modules.db.updates import v_2_0_2
        v_2_0_2.extract_logs_2_meta_dir()
        last_version = '2.0.2'

    if last_version == '2.0.2':
        from modules.db.updates import v_2_0_3
        v_2_0_3.add_parallel_deployment_execution_allowed()
        v_2_0_3.add_immediate_execution()
        last_version = '2.0.3'










if __name__ == '__main__':
    # This allows the script to be run directly to initialize the database
    print("Initializing meta file SQLite database...")
    # A left over WAL file must not be applied to the new database
    for db_file in [DB_FILE, f"{DB_FILE}-wal", f"{DB_FILE}-shm"]:
        if os.path.exists(db_file):
            os.remove(db_file)
            print(f"Removed existing database file: {db_file}")
    create_tables()
    print("Database and tables created.")
