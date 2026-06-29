import datetime
import logging
from modules.action_type import Action_type
from modules.db import app_sqlite
from modules import processing_user
from modules.stages import Stage




def create_action_log(action: Action_type, details: str|None=None, meta_file=None, stage: Stage|None=None) -> None:

  if meta_file is not None:
    create_processing_user(meta_file_id=meta_file.id, action=action, timestamp=datetime.datetime.now(), stage=stage.name if stage else None, details=details)




    

def create_processing_user(meta_file_id: int, action: processing_user.Action_type=None, stage: str=None, timestamp: datetime.datetime=None, details: str=None) -> processing_user.Processing_User:
    """Creates a new Processing_User instance and saves it to the database."""
    
    pu = processing_user.Processing_User(meta_file_id=meta_file_id, action=action, stage=stage, timestamp=timestamp, details=details)
    add_processing_user(pu)

    return pu
    


def get_processing_user_by_meta_id(meta_file_id: int) -> list:
    
    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM processing_users WHERE meta_file_id = ?", (meta_file_id,))
        processing_user_rows = c.fetchall()
        
        if len(processing_user_rows) == 0:
            return []
        
        return [dict(row) for row in processing_user_rows]
    
    return []



def add_processing_user(processing_user_obj: processing_user.Processing_User):
    """
    Saves a Processing_User object to the SQLite database.
    This function handles inserting or updating records across multiple tables.
    """
    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()

        c.execute('''
            INSERT INTO processing_users (meta_file_id, action, user, stage, timestamp, details)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            processing_user_obj.meta_file_id,
            processing_user_obj.action.value if processing_user_obj.action else None,
            processing_user_obj.user,
            processing_user_obj.stage,
            processing_user_obj.timestamp.isoformat() if processing_user_obj.timestamp else None,
            processing_user_obj.details
        ))
        processing_user_obj.id = c.lastrowid

        conn.commit()
    logging.info(f"Processing user for meta file ID {processing_user_obj.meta_file_id} saved to database.")
