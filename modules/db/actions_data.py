import sqlite3
import logging
import json
from modules.db import app_sqlite
from modules import workflow as wf
from modules import stages as s
from modules.stage_status import Status as Stage_Status
from modules import deploy_action as da






def create_action(stage_id: int|None=None, deploy_object_id: int|None=None, action_id: int|None=None) -> da.Deploy_Action:
    action = da.Deploy_Action()
    add_action(action=action, stage_id=stage_id, deploy_object_id=deploy_object_id, action_id=action_id)
    return action




def add_action(action: da.Deploy_Action, stage_id: int|None=None, deploy_object_id: int|None=None, action_id: int|None=None, cursor: sqlite3.Cursor|None=None):
    """
    Adds an action to the database for the given stage_id.

    Args:
        c (sqlite3.Cursor): Database cursor.
        stage_id (int): ID of the stage.
        deploy_object_id (int): ID of the deploy object.
        action (da.Deploy_Action): Action object to be added.
    """
    if cursor is not None:
        _add_action(action, cursor, stage_id, deploy_object_id, action_id)
        return

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()

        _save_action(action, cursor=c)
        conn.commit()



def _add_action(action: da.Deploy_Action, cursor: sqlite3.Cursor, stage_id: int|None=None, deploy_object_id: int|None=None, action_id: int|None=None):

    cursor.execute('''
        INSERT INTO actions (stage_id, deploy_object_id, action_id, sequence, cmd, status, 
                                processing_step, environment, run_in_new_job, 
                                execute_remote, check_error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        stage_id, deploy_object_id, action_id, action.sequence, action.cmd, action.status.value,
        action.processing_step, action.environment.value, action.run_in_new_job,
        action.execute_remote, action.check_error
    ))
    action_db_id = cursor.lastrowid
    
    if action_db_id is None:
        raise Exception(f"Failed to insert action '{action.cmd}' for stage_id {stage_id}.")
    action.id = action_db_id
    action.action_id = action_id
    action.deploy_object_id = deploy_object_id
    action.stage_id = stage_id





def save_action(action: da.Deploy_Action, cursor: sqlite3.Cursor|None=None, stage_id: int|None=None, deploy_object_id: int|None=None, action_id: int|None=None):

    if action.id is None:
        add_action(action=action, stage_id=stage_id, deploy_object_id=deploy_object_id, action_id=action_id, cursor=cursor)
        return

    if cursor is not None:
        _save_action(action, cursor)
        return

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()

        _save_action(action, c)
        conn.commit()



def _save_action(action: da.Deploy_Action, cursor: sqlite3.Cursor):
    cursor.execute('''
        update actions set sequence = ?, cmd = ?, status = ?, processing_step = ?, environment = ?, run_in_new_job = ?, execute_remote = ?, check_error = ?
        WHERE id = ?
    ''', (
        action.sequence, action.cmd, action.status.value, action.processing_step, action.environment.value, action.run_in_new_job, action.execute_remote, action.check_error, 
        action.id
    ))
    
    logging.debug(f"Saved action with ID {action.id} and command '{len(action.sub_actions)}' subactions to the database.")

    if action.sub_actions is not None and len(action.sub_actions) > 0:
        for sub_action in action.sub_actions:
            if sub_action.id is None:
                logging.debug(f"Add {sub_action.get_dict()=}")
                _add_action(sub_action, cursor, action_id=action.id)
            logging.debug(f"Save {sub_action.get_dict()=}")
            _save_action(sub_action, cursor)

    for history in action.run_history:
        cursor.execute('''
            update action_run_history set create_time = ?, status = ?, stdout = ?, stderr = ?
            WHERE id = ?
        ''', (
            history.create_time, history.status.value, history.stdout, history.stderr,
            history.id
        ))



def get_actions(stage_id: int|None=None, deploy_object_id: int|None=None, action_id: int|None=None) -> da.Deploy_Action_List_list:
    
    sql_dict: dict[str, str] = { 
        "stage_id": "SELECT * FROM actions WHERE stage_id = ?",
        "deploy_object_id": "SELECT * FROM actions WHERE deploy_object_id = ?",
        "action_id": "SELECT * FROM actions WHERE action_id = ?"
    }
    sql: str = ""
    param: tuple = ()

    if stage_id is not None:
        sql = sql_dict["stage_id"]
        param = (stage_id,)
    if deploy_object_id is not None:
        sql = sql_dict["deploy_object_id"]
        param = (deploy_object_id,)
    if action_id is not None:
        sql = sql_dict["action_id"]
        param = (action_id,)

    if len(sql) == 0:
        raise Exception("Either stage_id, deploy_object_id, or action_id must be provided.")

    with app_sqlite.get_db_connection() as conn:

        c = conn.cursor()
        c.execute(sql, param)

        action_rows = c.fetchall()
        actions = da.Deploy_Action_List_list()
        for row in action_rows:
            action_dict = dict(row)
            action_dict['status'] = da.Cmd_Status(action_dict['status'])
            action_dict['environment'] = da.Command_Type(action_dict['environment'])
            
            c.execute("SELECT * FROM action_run_history WHERE action_id = ?", (row['id'],))
            history_rows = c.fetchall()
            action_dict['run_history'] = [dict(hr) for hr in history_rows]
            
            action_obj = da.Deploy_Action(dict_data=action_dict)
            action_obj.sub_actions = get_actions(action_id=row['id'])
            actions.append(action_obj)

    return actions