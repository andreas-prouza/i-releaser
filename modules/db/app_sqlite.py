
import datetime
import glob
import sqlite3
import os
import logging
from etc import constants
from modules import errors, files
from modules.db import app_info_data


DB_FILE = os.path.abspath(constants.C_APP_DB_FILE)

# Number of database updates (see get_updates). Stored in the database as `PRAGMA user_version`.
SCHEMA_VERSION = 8

# Seconds to wait for a write lock of another process
DB_TIMEOUT = 30

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
    ('processing_jobs', 'meta_file_id'),
    ('processing_jobs', 'status'),
    ('meta_files', 'deploy_version_id'),
    ('meta_files', 'commit_hash'),
    ('login_failures', 'key'),
]



class Connection(sqlite3.Connection):
    """`with` commits (or rolls back) and closes the connection"""

    def __exit__(self, *args):
        result = super().__exit__(*args)
        self.close()
        return result



COMPOSITE_INDEXES = [
    ('idx_workflow_definitions_name', 'workflow_definitions', ['name']),
    ('idx_meta_files_status', 'meta_files', ['status']),
    ('idx_deploy_objects_object', 'deploy_objects', ['prod_lib', 'name', 'type', 'attribute']),
]



def get_db_connection(db_path=DB_FILE, *, timeout: float|None=None):
    """Establishes a connection to the SQLite database.

    Args:
        timeout: Seconds to wait for a lock of the database (default DB_TIMEOUT). Keyword only: tests replace
            the default of `db_path` with `__defaults__`.
    """

    conn = sqlite3.connect(db_path, timeout=DB_TIMEOUT if timeout is None else timeout, factory=Connection)
    conn.row_factory = sqlite3.Row

    # In WAL mode, commits don't need to be synced to disk (only checkpoints do).
    # An OS crash may lose the latest commits, but never corrupts the database.
    if conn.execute("PRAGMA journal_mode").fetchone()[0] == 'wal':
        conn.execute("PRAGMA synchronous=NORMAL")

    return conn



def get_db_file() -> str:
    return get_db_connection.__defaults__[0]



def update_changes(cursor: sqlite3.Cursor, table: str, row_id: int, values: dict, saved_values: dict|None) -> dict:
    """
    Updates only the columns which have changed since the row has been read.
    So copies of the same data (e.g. of parallel stages) don't overwrite each other with old values.

    Args:
        values (dict): Current values {column: value}
        saved_values (dict): Values when the row has been read or saved. None: all columns are updated

    Returns:
        dict: The new saved values

    Raises:
        ValueError: The row has no id (it isn't stored yet): `UPDATE … WHERE id = NULL` would change nothing
    """

    if row_id is None:
        raise ValueError(f"A row of {table} without id can't be updated")

    changes = {column: value for column, value in values.items() if saved_values is None or column not in saved_values or saved_values[column] != value}

    if len(changes) > 0:
        cursor.execute(f"UPDATE {table} SET {', '.join(f'{column} = ?' for column in changes)} WHERE id = ?", (*changes.values(), row_id))

    return values



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

        new_database = c.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'meta_files'").fetchone()[0] == 0


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
                fail_on_stderr BOOLEAN,
                timeout_seconds INTEGER,
                parallel_group TEXT,
                parallel BOOLEAN,
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

        # Queue of the processing service
        c.execute('''
            CREATE TABLE IF NOT EXISTS processing_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meta_file_id INTEGER,
                stage_id INTEGER,
                processing_step TEXT,
                continue_run BOOLEAN,
                user TEXT,
                status TEXT,
                error TEXT,
                create_time TEXT,
                start_time TEXT,
                end_time TEXT,
                pid INTEGER,
                heartbeat REAL, -- Epoch seconds
                run_at TEXT, -- Scheduled run: not before this time (UTC, '2026-11-24T21:00:00+00:00')
                FOREIGN KEY (meta_file_id) REFERENCES meta_files (id),
                FOREIGN KEY (stage_id) REFERENCES stages (id)
            )
        ''')

        # Failed logins, shared by all workers of the web app
        c.execute('''
            CREATE TABLE IF NOT EXISTS login_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL, -- "user:{user}" or "client:{address}"
                failed_at REAL NOT NULL -- Epoch seconds
            )
        ''')

        # Approvals of the four-eyes check (docs/features/four-eyes-check.md)
        c.execute('''
            CREATE TABLE IF NOT EXISTS stage_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meta_file_id INTEGER NOT NULL,
                stage_id INTEGER NOT NULL,
                user TEXT NOT NULL,
                time TEXT NOT NULL, -- UTC, ISO 8601
                content_hash TEXT NOT NULL, -- object list, custom data and compile list at the approval
                status TEXT NOT NULL, -- valid, invalid (changed afterwards), used (the stage has run)
                FOREIGN KEY (meta_file_id) REFERENCES meta_files (id),
                FOREIGN KEY (stage_id) REFERENCES stages (id)
            )
        ''')
        c.execute("CREATE INDEX IF NOT EXISTS idx_stage_approvals_stage_id ON stage_approvals (stage_id)")

        # Security events (docs/features/audit-log.md): only added, each row has the hash of the one before (hash chain)
        c.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TEXT NOT NULL, -- UTC, ISO 8601
                user TEXT,
                client TEXT,
                event TEXT NOT NULL,
                object TEXT,
                details TEXT, -- JSON
                result TEXT NOT NULL, -- ok, failed
                prev_hash TEXT NOT NULL,
                hash TEXT NOT NULL
            )
        ''')
        c.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_time ON audit_log (time)")

        # Two-factor authentication (docs/features/two-factor-authentication.md). A new table: created here, no update needed
        c.execute('''
            CREATE TABLE IF NOT EXISTS user_mfa (
                user TEXT PRIMARY KEY, -- in lower case
                secret TEXT NOT NULL, -- Base32
                enabled INTEGER NOT NULL DEFAULT 0, -- 0: set up, not confirmed with a code yet
                created_at TEXT NOT NULL,
                last_step INTEGER, -- time step of the last accepted code (a code is accepted only once)
                recovery_codes TEXT NOT NULL DEFAULT '[]' -- JSON list of SHA-256 hashes, each removed when used
            )
        ''')

        # API tokens (docs/features/api-v2.md#tokens), before in webapp/etc/keys.json (taken over by app_login.migrate_keys_file)
        c.execute('''
            CREATE TABLE IF NOT EXISTS api_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT NOT NULL, -- in lower case
                name TEXT NOT NULL,
                key_hash TEXT NOT NULL UNIQUE, -- SHA-256 of the token
                masked TEXT, -- the end of the token, to recognize it
                scope TEXT NOT NULL, -- read (only GET) or write
                created_at TEXT NOT NULL, -- UTC, ISO 8601
                expires_at TEXT, -- UTC, ISO 8601; NULL: never (C_TOKEN_MAX_DAYS = 0)
                last_used_at TEXT,
                legacy INTEGER NOT NULL DEFAULT 0, -- format before 2026-10
                UNIQUE (user, name)
            )
        ''')
        c.execute("CREATE INDEX IF NOT EXISTS idx_api_tokens_user ON api_tokens (user)")

        # Outbox of the notifications (docs/features/notifications.md). A new table: created here, no update needed
        c.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL, -- UTC, ISO 8601
                event TEXT NOT NULL,
                meta_file_id INTEGER,
                channel TEXT NOT NULL, -- name of the channel in etc/notifications.json
                recipients TEXT NOT NULL DEFAULT '[]', -- JSON list of e-mail addresses (e-mail channels)
                message TEXT NOT NULL, -- JSON: the values of the deployment at the event
                status TEXT NOT NULL, -- pending, sending, sent, failed
                attempts INTEGER NOT NULL DEFAULT 0, -- failed attempts
                next_attempt_at TEXT NOT NULL, -- UTC, ISO 8601
                claimed_at TEXT,
                sent_at TEXT,
                last_error TEXT
            )
        ''')
        c.execute("CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications (status, next_attempt_at)")

        for table, column in INDEXED_COLUMNS:
            c.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_{column} ON {table} ({column})")

        # Filters of the lists and of the permission check (docs/features/core-redesign.md, step 2)
        for name, table, columns in COMPOSITE_INDEXES:
            c.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({', '.join(columns)})")

        if new_database:
            c.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

        conn.commit()
    logging.info("SQLite tables for meta files created successfully.")

    enable_wal(db_path)





def get_updates() -> list[tuple]:
    """All updates of the database as (schema version after the update, function), in the order they have to be run"""

    from modules.db.updates import v_2_0_1, v_2_0_2, v_2_0_3, v_3_1_0, v_4_1_0

    return [
        (1, v_2_0_1.add_compression),
        (2, v_2_0_2.extract_logs_2_meta_dir),
        (3, v_2_0_3.add_parallel_deployment_execution_allowed),
        (4, v_2_0_3.add_immediate_execution),
        (5, v_3_1_0.remove_tokens_from_custom_data),
        (6, v_3_1_0.add_action_options),
        (7, v_3_1_0.add_parallel_options),
        (8, v_4_1_0.add_job_run_at),
    ]



def get_schema_version() -> int:
    """
    Version of the database, independent of the configuration.
    A database of an older i-Releaser has no version yet: it's taken from the application version of its last start.
    """

    with get_db_connection() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]

    if version > 0:
        return version

    app_info: dict | None = app_info_data.get_app_info()

    return {'2.0.0': 0, '2.0.1': 1, '2.0.2': 2}.get(app_info['version'] if app_info else None, 4)



def set_schema_version(version: int) -> None:

    with get_db_connection() as conn:
        conn.execute(f"PRAGMA user_version = {int(version)}")



def check_schema_version() -> None:
    """
    Raises:
        errors.App_Error: If the database is older than the code. It's updated at the start of the web app.
    """

    version = get_schema_version()

    if version < SCHEMA_VERSION:
        raise errors.App_Error(f"Database has version {version}, but version {SCHEMA_VERSION} is needed. Start the web app first: it updates the database.")



def backup_database(schema_version: int) -> str:
    """
    Copies the database into the directory `backup` next to it and keeps the newest C_DB_BACKUP_COUNT copies.

    Returns:
        str: File name of the backup
    """

    db_file = get_db_file()
    backup_dir = os.path.join(os.path.dirname(db_file), 'backup')
    os.makedirs(backup_dir, exist_ok=True)

    backup_file = os.path.join(backup_dir, f"app-{schema_version}-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.sqlite")

    with get_db_connection() as conn, sqlite3.connect(backup_file) as backup_conn:
        conn.backup(backup_conn)
    backup_conn.close()

    for old_backup in sorted(glob.glob(os.path.join(backup_dir, 'app-*.sqlite')), key=os.path.getmtime, reverse=True)[constants.C_DB_BACKUP_COUNT:]:
        os.remove(old_backup)

    logging.info(f"Database saved to {backup_file}")
    return backup_file



def restore_database(backup_file: str) -> None:

    with sqlite3.connect(backup_file) as backup_conn, get_db_connection() as conn:
        backup_conn.backup(conn)
    backup_conn.close()

    logging.info(f"Database restored from {backup_file}")



def check_updates() -> None:
    """
    Runs the updates the database hasn't got yet, after a backup. If one fails, the database is restored and the error is raised.
    Multiple workers start at the same time, but only one of them does the updates.
    """

    with files.lock(f"{get_db_file()}.update.lock"):

        version = get_schema_version()
        updates = [update for update in get_updates() if update[0] > version]

        if len(updates) == 0:
            set_schema_version(version)
            return

        logging.info(f"Database has version {version}. Updating to version {updates[-1][0]}.")
        backup_file = backup_database(version)

        try:
            for update_version, update in updates:
                update()
                set_schema_version(update_version)

        except Exception as e:
            logging.exception(e, stack_info=True)
            restore_database(backup_file)
            raise errors.App_Error(f"Database update to version {update_version} failed: {e}. The database has been restored from {backup_file}.") from e



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
