import sqlite3
import json
from modules.db import app_sqlite
from modules import workflow as wf
from modules import stages as s
from modules.stage_status import Status as Stage_Status
from modules import deploy_action as da
from modules.db import actions_data


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
            INSERT INTO stages (meta_file_id, name, description, host, base_dir, remote_dir, status, build_dir, next_stages, next_stage_ids, 
                                after_stages_finished, clear_files, lib_replacement_necessary, lib_mapping, processing_steps, execute_remote, create_time, update_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp, current_timestamp)
        ''', (
            meta_file_id, stage.name, stage.description, stage.host, stage.base_dir, stage.remote_dir, stage.status.value, stage.build_dir,
            json.dumps(stage.next_stages), json.dumps(stage.next_stage_ids),
            json.dumps(stage.after_stages_finished), json.dumps(stage.clear_files), json.dumps(stage.lib_replacement_necessary), 
            json.dumps(stage.lib_mapping), json.dumps(stage.processing_steps), stage.execute_remote
        ))
        stage_db_id = c.lastrowid

        conn.commit()

        for action in stage.actions:
            actions_data.add_action(stage_id=stage_db_id, action=action)

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
            stage_dict['next_stages'] = json.loads(stage_dict['next_stages']) if stage_dict['next_stages'] else []
            stage_dict['next_stage_ids'] = json.loads(stage_dict['next_stage_ids']) if stage_dict['next_stage_ids'] else []
            stage_dict['after_stages_finished'] = json.loads(stage_dict['after_stages_finished']) if stage_dict['after_stages_finished'] else []
            stage_dict['processing_steps'] = json.loads(stage_dict['processing_steps']) if stage_dict['processing_steps'] else []
            stage_dict['lib_mapping'] = json.loads(stage_dict['lib_mapping']) if stage_dict['lib_mapping'] else {}
            stage_dict['status'] = Stage_Status(stage_dict['status'])
            
            stage_dict['actions'] = actions_data.get_actions(stage_id=row['id'])
            stage_obj = s.Stage(dict=stage_dict)
            
            stages.append(stage_obj)
    return stages




def get_stage(stage_id: int) -> s.Stage | None:

    stage_obj = None
    
    with app_sqlite.get_db_connection() as conn:

        c = conn.cursor()
        c.execute("SELECT * FROM stages WHERE id = ?", (stage_id,))
        stage_rows = c.fetchall()
        stages = s.Stage_List_list()
        
        row = stage_rows[0] if stage_rows else None
        if row is None:
            return None
        stage_dict = dict(row)
        stage_dict['next_stages'] = json.loads(stage_dict['next_stages']) if stage_dict['next_stages'] else []
        stage_dict['next_stage_ids'] = json.loads(stage_dict['next_stage_ids']) if stage_dict['next_stage_ids'] else []
        stage_dict['after_stages_finished'] = json.loads(stage_dict['after_stages_finished']) if stage_dict['after_stages_finished'] else []
        stage_dict['processing_steps'] = json.loads(stage_dict['processing_steps']) if stage_dict['processing_steps'] else []
        stage_dict['lib_mapping'] = json.loads(stage_dict['lib_mapping']) if stage_dict['lib_mapping'] else {}
        stage_dict['status'] = Stage_Status(stage_dict['status'])
        
        stage_dict['actions'] = actions_data.get_actions(stage_id=row['id'])

        stage_obj = s.Stage(dict=stage_dict)
        
    return stage_obj



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
        update stages set status = ?, next_stages = ?, next_stage_ids = ?, after_stages_finished = ?, lib_mapping = ?, update_time = ?
        WHERE id = ?
    ''', (
        stage.status.value, json.dumps(stage.next_stages), json.dumps(stage.next_stage_ids),
        json.dumps(stage.after_stages_finished), json.dumps(stage.lib_mapping), stage.update_time,
        stage.id
    ))

    for action in stage.actions:
        actions_data.save_action(action, cursor, stage_id=stage.id)


