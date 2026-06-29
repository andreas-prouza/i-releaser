import sqlite3
import json
from modules.db import app_sqlite
from modules import workflow as wf
from modules import stages as s
from modules.stage_status import Status as Stage_Status
from modules import deploy_action as da


def create_stage(meta_file_id: int, name:str, workflow: wf.Workflow) -> s.Stage:
    stage = s.Stage.get_stage_from_workflow(workflow, name)
    _add_stage(meta_file_id=meta_file_id, stage=stage)
    return stage


def _add_stage(meta_file_id: int, stage: s.Stage):
    """
    Adds a stage to the database for the given meta_file_id.

    Args:
        c (sqlite3.Cursor): Database cursor.
        meta_file_id (int): ID of the meta file.
        stage (s.Stage): Stage object to be added.
    """
    with app_sqlite.get_db_connection() as conn:

        c = conn.cursor()
        c.execute('''
            INSERT INTO stages (meta_file_id, name, description, status, next_stages, next_stage_ids, 
                                after_stages_finished, processing_steps, lib_mapping)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            meta_file_id, stage.name, stage.description, stage.status.value,
            json.dumps(stage.next_stages), json.dumps(stage.next_stage_ids),
            json.dumps(stage.after_stages_finished), json.dumps(stage.processing_steps),
            json.dumps(stage.lib_mapping)
        ))
        stage_db_id = c.lastrowid

        conn.commit()

        for action in stage.actions:
            _add_action(stage_id=stage_db_id, action=action)

        if stage_db_id is None:
            raise Exception(f"Failed to insert stage '{stage.name}' for meta_file_id {meta_file_id}.")
        stage.id = stage_db_id



def _add_action(stage_id: int, action: da.Deploy_Action):
    """
    Adds an action to the database for the given stage_id.

    Args:
        c (sqlite3.Cursor): Database cursor.
        stage_id (int): ID of the stage.
        action (da.Deploy_Action): Action object to be added.
    """
    with app_sqlite.get_db_connection() as conn:

        c = conn.cursor()
        c.execute('''
            INSERT INTO actions (stage_id, sequence, cmd, status, 
                                 processing_step, environment, run_in_new_job, 
                                 execute_remote, check_error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            stage_id, action.sequence, action.cmd, action.status.value,
            action.processing_step, action.environment.value, action.run_in_new_job,
            action.execute_remote, action.check_error
        ))
        action_db_id = c.lastrowid
        conn.commit()
        
        if action_db_id is None:
            raise Exception(f"Failed to insert action '{action.cmd}' for stage_id {stage_id}.")
        action.id = action_db_id

        conn.commit()




def get_stages(meta_file_id: int) -> s.Stage_List_list:

    with app_sqlite.get_db_connection() as conn:

        c = conn.cursor()
        c.execute("SELECT * FROM stages WHERE meta_file_id = ?", (meta_file_id,))
        stage_rows = c.fetchall()
        stages = s.Stage_List_list()
        
        for row in stage_rows:
            stage_dict = dict(row)
            stage_dict['next_stages'] = json.loads(stage_dict['next_stages'])
            stage_dict['next_stage_ids'] = json.loads(stage_dict['next_stage_ids'])
            stage_dict['after_stages_finished'] = json.loads(stage_dict['after_stages_finished'])
            stage_dict['processing_steps'] = json.loads(stage_dict['processing_steps'])
            stage_dict['lib_mapping'] = json.loads(stage_dict['lib_mapping'])
            stage_dict['status'] = Stage_Status(stage_dict['status'])
            
            c.execute("SELECT * FROM actions WHERE stage_id = ?", (row['id'],))
            action_rows = c.fetchall()
            actions = da.Deploy_Action_List_list()
            for action_row in action_rows:
                action_dict = dict(action_row)
                c.execute("SELECT * FROM action_run_history WHERE action_id = ?", (action_row['id'],))
                history_rows = c.fetchall()
                action_dict['run_history'] = [dict(hr) for hr in history_rows]
                actions.add_action(da.Deploy_Action(dict=action_dict))
            stage_dict['actions'] = actions
            
            stage_obj = s.Stage(dict=stage_dict)
            stages.append(stage_obj)
    return stages



def save_stages(stages: s.Stage_List_list, cursor: sqlite3.Cursor=None):
    
    for stage in stages:
        save_stage(stage, cursor)


def save_stage(stage: s.Stage, cursor: sqlite3.Cursor=None):

    if cursor is not None:
        _save_stage(stage, cursor)
        return

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        _save_stage(stage, c)
        
        conn.commit()




def _save_stage(stage: s.Stage, cursor: sqlite3.Cursor):
    cursor.execute('''
        update stages set status = ?, next_stages = ?, next_stage_ids = ?, after_stages_finished = ?
        WHERE id = ?
    ''', (
        stage.status.value, json.dumps(stage.next_stages), json.dumps(stage.next_stage_ids),
        json.dumps(stage.after_stages_finished), 
        stage.id
    ))

    for action in stage.actions:
        save_action(action, cursor)



def save_action(action: da.Deploy_Action, cursor: sqlite3.Cursor=None):

    if cursor is not None:
        _save_action(action, cursor)
        return

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()

        _save_action(action, c)
        conn.commit()


def _save_action(action: da.Deploy_Action, cursor: sqlite3.Cursor):
    cursor.execute('''
        update actions set status = ?, check_error = ?
        WHERE id = ?
    ''', (
        action.status.value, action.check_error,
        action.id
    ))

    for history in action.run_history:
        cursor.execute('''
            update action_run_history set create_time = ?, status = ?, stdout = ?, stderr = ?
            WHERE id = ?
        ''', (
            history.create_time, history.status.value, history.stdout, history.stderr,
            history.id
        ))