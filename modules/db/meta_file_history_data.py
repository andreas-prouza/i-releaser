from io import StringIO
import os
import logging
from modules.db import app_sqlite
from modules.db.meta_file_data import get_meta_dir
from modules import meta_file_history as mfh
from modules import files





def create_new_meta_file_history(log: StringIO=None, create_time=None, meta_file_id: int=None, dict: dict={}) -> mfh.Meta_File_History:
    """Creates a new Meta_File_History instance and saves it to the database."""
    
    mfh_obj = mfh.Meta_File_History(
        log=log,
        create_time=create_time,
        meta_file_id=meta_file_id,
        dict=dict
    )

    add_meta_file_history(mfh_obj)

    return mfh_obj
    



def get_run_history_by_id(id: int) -> mfh.Meta_File_History|None:

    run_history: mfh.Meta_File_History|None = None

    with app_sqlite.get_db_connection() as conn:
        
        c = conn.cursor()
        c.execute("SELECT * FROM run_history WHERE id = ?", (id,))
        run_history_rows = c.fetchall()
        
        if len(run_history_rows) == 0:
            return None
        
        run_history = mfh.Meta_File_History(id=run_history_rows[0]['id'], meta_file_id=run_history_rows[0]['meta_file_id'], create_time=run_history_rows[0]['create_time'], log=run_history_rows[0]['log'])

        if run_history.log and isinstance(run_history.log, str) and run_history.log.startswith("file://"):
            run_history.log = files.readFile(run_history.log[7:])

    return run_history






def add_meta_file_history(meta_file_history: mfh.Meta_File_History):
    """
    Saves a Meta_File_History object to the SQLite database.
    This function handles inserting or updating records across multiple tables.
    """

    if meta_file_history.meta_file_id is None:
        raise ValueError("meta_file_id must be set before saving Meta_File_History.")

    
    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()

        if meta_file_history.log is None or isinstance(meta_file_history.log, StringIO) and meta_file_history.log.getvalue() == "":
            return

        log = meta_file_history.log
        if isinstance(log, StringIO):
            log = log.getvalue()

        meta_dir:str|None = get_meta_dir(cursor=c, meta_file_id=meta_file_history.meta_file_id)
        if meta_dir is None:
            raise Exception(f"Meta directory not found for meta file ID {meta_file_history.meta_file_id}. Cannot save run history logs.")
        
        c.execute('''
            INSERT INTO run_history (meta_file_id, create_time)
            VALUES (?, ?)
        ''', (
            meta_file_history.meta_file_id, meta_file_history.create_time
        ))
        meta_file_history.id = c.lastrowid

        if log is None or len(log) == 0:
            return
        
        log_file_path = os.path.join(meta_dir, "logs", "run_history", f"{meta_file_history.id}.log")
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        files.writeText(meta_file_history.log, log_file_path)
        meta_file_history.log = f"file://{log_file_path}"

        c.execute('''
                    UPDATE run_history SET log = ?
                    WHERE id = ? 
                ''', (
                    meta_file_history.log, meta_file_history.id
                ))


        conn.commit()
    logging.info(f"Meta file history for meta file ID {meta_file_history.meta_file_id} saved to database.")
