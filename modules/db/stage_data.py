import sqlite3
import json
from modules.db import app_sqlite
from modules import workflow as wf
from modules import stages as s
from modules.stage_status import Status as Stage_Status
from modules import deploy_action as da


def create_stage(meta_file_id: int, name:str, workflow: wf.Workflow) -> s.Stage:
    stage = s.Stage.get_stage_from_workflow(workflow, name)
    add_stage(meta_file_id=meta_file_id, stage=stage)
    return stage


def add_stage(meta_file_id: int, stage: s.Stage):
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
            json.dumps(stage.next_stages.get_all_names()), json.dumps(stage.next_stage_ids),
            json.dumps(stage.after_stages_finished), json.dumps(stage.processing_steps),
            json.dumps(stage.lib_mapping)
        ))
        stage_db_id = c.lastrowid
        if stage_db_id is None:
            raise Exception(f"Failed to insert stage '{stage.name}' for meta_file_id {meta_file_id}.")
        stage.id = stage_db_id




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



def save_stages(c: sqlite3.Cursor, meta_file_id: int, stages: s.Stage_List_list):
    c.execute("DELETE FROM stages WHERE meta_file_id = ?", (meta_file_id,))
    for stage in stages:
        c.execute('''
            INSERT INTO stages (meta_file_id, name, description, status, next_stages, next_stage_ids, 
                              after_stages_finished, processing_steps, lib_mapping)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            meta_file_id, stage.name, stage.description, stage.status.value,
            json.dumps(stage.next_stages.get_all_names()), json.dumps(stage.next_stage_ids),
            json.dumps(stage.after_stages_finished), json.dumps(stage.processing_steps),
            json.dumps(stage.lib_mapping)
        ))
        stage_db_id = c.lastrowid

        c.execute("DELETE FROM actions WHERE stage_id = ?", (stage_db_id,))
        for action in stage.actions:
            c.execute('''
                INSERT INTO actions (stage_id, sequence, cmd, status, stage_name, processing_step, environment, run_in_new_job, execute_remote, check_error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                stage_db_id, action.sequence, action.cmd, action.status.value, stage.name, action.processing_step,
                action.environment.value, action.run_in_new_job, action.execute_remote, action.check_error
            ))
            action_db_id = c.lastrowid

            c.execute("DELETE FROM action_run_history WHERE action_id = ?", (action_db_id,))
            for history in action.run_history:
                c.execute('''
                    INSERT INTO action_run_history (action_id, start_time, end_time, rc, log)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    action_db_id, history.start_time, history.end_time, history.rc, history.log
                ))
