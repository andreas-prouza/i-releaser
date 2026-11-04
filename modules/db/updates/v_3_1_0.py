import json
import logging
import sqlite3

from modules.db import app_sqlite, compression



def remove_tokens_from_custom_data():
    """`GET /api/start_workflow` used to store the API token of the request in the custom data"""

    logging.info("Removing API tokens from custom data...")

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id, custom_data FROM meta_files WHERE custom_data IS NOT NULL")

        for row in c.fetchall():

            custom_data = json.loads(compression.decompress_field(row['custom_data']))

            if not isinstance(custom_data, dict) or 'auth-token' not in custom_data:
                continue

            del custom_data['auth-token']
            c.execute("UPDATE meta_files SET custom_data = ? WHERE id = ?",
                      (compression.compress_field(json.dumps(custom_data)) if custom_data else None, row['id']))

        conn.commit()



def add_action_options():

    logging.info("Adding fail_on_stderr and timeout_seconds columns if not exists...")
    _add_action_columns(['fail_on_stderr BOOLEAN', 'timeout_seconds INTEGER'])



def add_parallel_options():

    logging.info("Adding parallel_group and parallel columns if not exists...")
    _add_action_columns(['parallel_group TEXT', 'parallel BOOLEAN'])



def _add_action_columns(columns: list[str]):

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()

        for column in columns:
            try:
                c.execute(f"ALTER TABLE actions ADD COLUMN {column}")

            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise e
                logging.warning(f"Could not add column {column}: {e}")

        conn.commit()
