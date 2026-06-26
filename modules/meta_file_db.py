import sqlite3
import json
import logging
import os
from typing import Union

from etc import constants

DB_FILE = os.path.abspath(constants.C_META_DB_FILE)

def init_db():
    """Initializes the database and creates the meta_files table if it doesn't exist."""
    db_dir = os.path.dirname(DB_FILE)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
        
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS meta_files (
                file_name TEXT PRIMARY KEY,
                project TEXT,
                deploy_version INTEGER,
                status TEXT,
                create_time TEXT,
                update_time TEXT,
                data TEXT
            )
        ''')
        conn.commit()

def upsert_meta_file(meta_file_instance):
    """Inserts or updates a meta file record in the database."""
    data = meta_file_instance.get_all_data_as_dict()
    
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        
        # Ensure table exists
        init_db()
        
        cursor.execute('''
            INSERT INTO meta_files (file_name, project, deploy_version, status, create_time, update_time, data)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_name) DO UPDATE SET
                project=excluded.project,
                deploy_version=excluded.deploy_version,
                status=excluded.status,
                create_time=excluded.create_time,
                update_time=excluded.update_time,
                data=excluded.data
        ''', (
            meta_file_instance.file_name,
            meta_file_instance.project,
            meta_file_instance.deploy_version,
            meta_file_instance.status.value,
            meta_file_instance.create_time,
            meta_file_instance.update_time,
            json.dumps(data)
        ))
        conn.commit()
        logging.debug(f"Upserted meta file {meta_file_instance.file_name} to sqlite db.")

def get_meta_file(file_name: str) -> Union['Meta_File', None]:
    """
    Retrieves a meta file from the database by its file name.

    Args:
        file_name (str): The absolute path to the meta file.

    Returns:
        Meta_File | None: The reconstructed Meta_File object, or None if not found.
    """
    conn = None
    try:
        db_path = os.path.join(constants.C_LOCAL_BASE_DIR, "etc", "meta.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT data FROM meta_files WHERE file_name = ?", (file_name,))
        row = cursor.fetchone()

        if row:
            data = json.loads(row[0])
            from modules.meta_file import Meta_File
            return Meta_File(imported_from_dict=data)
        return None
    except sqlite3.Error as e:
        logging.error(f"Database error in get_meta_file: {e}")
        return None
    finally:
        if conn:
            conn.close()
