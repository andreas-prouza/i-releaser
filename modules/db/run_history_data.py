from io import StringIO
import sqlite3
import json
import logging
from etc import constants
from modules.db import app_sqlite
from modules import meta_file as mf
from modules import stages as s
from modules.stage_status import Status as Stage_Status
from modules import deploy_object as do
from modules import deploy_action as da
from modules import workflow as wf
from modules import run_history
from modules import deploy_version as dv
from modules.meta_file_status import Meta_file_status
from modules.db import stage_data





def create_new_run_history(action_id: int) -> run_history.Run_History:
    """Creates a new Run_History instance and saves it to the database."""
    
    rh_obj = run_history.Run_History(action_id=action_id)
    add_run_history(rh_obj)

    return rh_obj
    





def get_run_history_by_id(id: int) -> run_history.Run_History|None:

    run_history_obj: run_history.Run_History|None = None

    with app_sqlite.get_db_connection() as conn:
        
        c = conn.cursor()
        c.execute("SELECT * FROM action_run_history WHERE id = ?", (id,))
        run_history_rows = c.fetchall()
        
        if len(run_history_rows) == 0:
            return None
        
        run_history_obj = run_history.Run_History(
                                id=run_history_rows[0]['id'], 
                                action_id=run_history_rows[0]['action_id'], 
                                create_time=run_history_rows[0]['create_time'], 
                                status=run_history_rows[0]['status'],
                                stdout=run_history_rows[0]['stdout'],
                                stderr=run_history_rows[0]['stderr'])

    return run_history_obj








def add_run_history(run_history_obj: run_history.Run_History):
    """
    Saves a Run_History object to the SQLite database.
    This function handles inserting or updating records across multiple tables.
    """
    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()

        c.execute('''
            INSERT INTO action_run_history (action_id, create_time)
            VALUES (?, ?)
        ''', (
            run_history_obj.action_id, run_history_obj.create_time
        ))
        run_history_obj.id = c.lastrowid

        conn.commit()
    logging.info(f"Run history for action ID {run_history_obj.action_id} saved to database.")
