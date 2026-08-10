
import sqlite3
import os
import logging
from etc import constants
from modules.db import app_sqlite, compression
from modules.db import app_info_data
from modules import files

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

        conn.commit()
    logging.info("SQLite tables for meta files created successfully.")





def check_updates():

    app_info: dict | None = app_info_data.get_app_info()
    if app_info is None:
        return

    last_version = app_info.get("version", "0.0.0")
    logging.info(f"Last app version in database: {last_version}")

    if last_version == '2.0.0':
        add_compression()
        last_version = '2.0.1'

    if last_version == '2.0.1':
        extract_logs_2_meta_dir()
        last_version = '2.0.2'




def extract_logs_2_meta_dir():
    logging.info("Moving logs to meta directory...")

    
    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()


        ###################################################
        # Run_History
        ###################################################

        c.execute("""select rh.*, mf.meta_dir  from meta_files mf
                        left join run_history rh on rh.meta_file_id = mf.id 
                     where rh.log is not null and rh.log <> '' and mf.meta_dir is not null and mf.meta_dir <> '' """)
        rows = c.fetchall()

        for row in rows:

            if row['log'] is None or len(row['log']) == 0 or (isinstance(row['log'], str) and row['log'].startswith("file://")):
                continue  # Skip if log is None or empty

            meta_dir = row['meta_dir']
            id = row['id']
            log_file_path = os.path.join(meta_dir, "logs", "run_history", f"{id}.log")
            log = compression.decompress_field(row['log'])

            # Write the combined logs to the processing.log file in the meta directory
            os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
            files.writeText(log, log_file_path)

            c.execute("UPDATE run_history SET log = ? where id = ?", (f"file://{log_file_path}", id))


        ###################################################
        # Action_Run_History
        ###################################################

        c.execute("""select arh.*, mf.meta_dir  from meta_files mf
                        INNER join deploy_objects do on do.meta_file_id = mf.id 
                        INNER join actions a on a.deploy_object_id  = do.id
                        INNER join action_run_history arh on arh.action_id = a.id
                    where mf.meta_dir is not null and mf.meta_dir <> ''
                    union all
                    select arh.*, mf.meta_dir  from meta_files mf
                        INNER join stages s on s.meta_file_id = mf.id 
                        INNER join actions a on a.stage_id = s.id
                        INNER join action_run_history arh on arh.action_id = a.id
                    where mf.meta_dir is not null and mf.meta_dir <> ''
                    union all
                    select arh.*, mf.meta_dir  from meta_files mf
                        INNER join stages s on s.meta_file_id = mf.id 
                        INNER join actions a on a.stage_id = s.id
                        inner join actions a2 on a2.action_id = a.id
                        INNER join action_run_history arh on arh.action_id = a2.id
                    where mf.meta_dir is not null and mf.meta_dir <> '' """)
        rows = c.fetchall()

        for row in rows:

            meta_dir = row['meta_dir']
            id = row['id']

            if row['stdout'] is not None and len(row['stdout']) > 0 and not (isinstance(row['stdout'], str) and row['stdout'].startswith("file://")):
                stdout_file_path = os.path.join(meta_dir, "logs", "action_run_history", f"{id}_stdout.log")
                os.makedirs(os.path.dirname(stdout_file_path), exist_ok=True)
                files.writeText(compression.decompress_field(row['stdout']), stdout_file_path)
                c.execute("UPDATE action_run_history SET stdout = ? where id = ?", (f"file://{stdout_file_path}", id))

            if row['stderr'] is not None and len(row['stderr']) > 0 and not (isinstance(row['stderr'], str) and row['stderr'].startswith("file://")):
                stderr_file_path = os.path.join(meta_dir, "logs", "action_run_history", f"{id}_stderr.log")
                os.makedirs(os.path.dirname(stderr_file_path), exist_ok=True)
                files.writeText(compression.decompress_field(row['stderr']), stderr_file_path)
                c.execute("UPDATE action_run_history SET stderr = ? where id = ?", (f"file://{stderr_file_path}", id))



        #################################################
        # Commit the transaction and close the connection
        #################################################

        conn.commit()


        #################################################
        # Reclaim space after compression
        #################################################
        c.execute("VACUUM")




def add_compression():

    logging.info("Starting compression of text fields in the database...")

    with app_sqlite.get_db_connection() as conn:

        c = conn.cursor()


        ########################################
        # meta_files
        ########################################
        c.execute("SELECT id, custom_data FROM meta_files")
        rows = c.fetchall()

        update_data = []

        # 2. Loop through the rows and compress the text
        for rowid, custom_data in rows:

            if not custom_data:
                continue  # Skip if custom_data is None or empty

            compressed_custom_data = compression.compress_field(custom_data)

            # Append a tuple formatted for our UPDATE statement: (val1, id)
            update_data.append((compressed_custom_data, rowid))

        # 3. Batch update the table with the new BLOB (binary) data
        c.executemany("UPDATE meta_files SET custom_data = ? WHERE id = ?", update_data)


        ########################################
        # workflow_definitions
        ########################################
        c.execute("SELECT id, definition FROM workflow_definitions")
        rows = c.fetchall()

        update_data = []

        # 2. Loop through the rows and compress the text
        for rowid, definition in rows:

            if not definition:
                continue  # Skip if definition is None or empty

            compressed_definition = compression.compress_field(definition)

            # Append a tuple formatted for our UPDATE statement: (val1, id)
            update_data.append((compressed_definition, rowid))

        # 3. Batch update the table with the new BLOB (binary) data
        c.executemany("UPDATE workflow_definitions SET definition = ? WHERE id = ?", update_data)



        ########################################
        # run_history
        ########################################
        c.execute("SELECT id, log FROM run_history")
        rows = c.fetchall()

        update_data = []

        # 2. Loop through the rows and compress the text
        for rowid, log in rows:

            if not log:
                continue  # Skip if log is None or empty
            
            compressed_log = compression.compress_field(log)

            # Append a tuple formatted for our UPDATE statement: (val1, id)
            update_data.append((compressed_log, rowid))

        # 3. Batch update the table with the new BLOB (binary) data
        c.executemany("UPDATE run_history SET log = ? WHERE id = ?", update_data)


        ########################################
        # action_run_history
        ########################################
        c.execute("SELECT id, stdout, stderr FROM action_run_history")
        rows = c.fetchall()

        update_data = []

        # 2. Loop through the rows and compress the text
        for rowid, stdout, stderr in rows:

            if not stdout and not stderr:
                continue  # Skip if both stdout and stderr are None or empty

            compressed_stdout = compression.compress_field(stdout)
            compressed_stderr = compression.compress_field(stderr)

            logging.info(f"bevore Compressing action_run_history id={rowid}: stdout size={len(stdout) if stdout else 0}, stderr size={len(stderr) if stderr else 0}")
            logging.info(f"after Compressing action_run_history id={rowid}: stdout size={len(compressed_stdout) if compressed_stdout else 0}, stderr size={len(compressed_stderr) if compressed_stderr else 0}")
            
            # Append a tuple formatted for our UPDATE statement: (val1, val2, id)
            update_data.append((compressed_stdout, compressed_stderr, rowid))

        # 3. Batch update the table with the new BLOB (binary) data
        c.executemany("UPDATE action_run_history SET stdout = ?, stderr = ? WHERE id = ?", update_data)




        #################################################
        # Commit the transaction and close the connection
        #################################################

        conn.commit()


        #################################################
        # Reclaim space after compression
        #################################################
        c.execute("VACUUM")









if __name__ == '__main__':
    # This allows the script to be run directly to initialize the database
    print("Initializing meta file SQLite database...")
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        print(f"Removed existing database file: {DB_FILE}")
    create_tables()
    print("Database and tables created.")
