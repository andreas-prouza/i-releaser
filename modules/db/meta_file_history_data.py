from io import StringIO
import logging
from modules.db import app_sqlite, compression
from modules import meta_file_history as mfh





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
        
        run_history = mfh.Meta_File_History(id=run_history_rows[0]['id'], meta_file_id=run_history_rows[0]['meta_file_id'], create_time=run_history_rows[0]['create_time'], log=compression.decompress_field(run_history_rows[0]['log']))

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

        c.execute('''
            INSERT INTO run_history (meta_file_id, create_time, log)
            VALUES (?, ?, ?)
        ''', (
            meta_file_history.meta_file_id, meta_file_history.create_time, compression.compress_field(meta_file_history.log.getvalue()) if meta_file_history.log else None
        ))
        meta_file_history.id = c.lastrowid

        conn.commit()
    logging.info(f"Meta file history for meta file ID {meta_file_history.meta_file_id} saved to database.")
