import datetime
import sqlite3
import json
from modules import state
from modules.db import app_sqlite
from modules import workflow as wf
from modules import stages as s
from modules.stage_status import Status as Stage_Status
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
                                after_stages_finished, clear_files, lib_replacement_necessary, lib_mapping, processing_steps, execute_remote, create_time, update_time, run_immediate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp, current_timestamp, ?)
        ''', (
            meta_file_id, stage.name, stage.description, stage.host, stage.base_dir, stage.remote_dir, stage.status.value, stage.build_dir,
            json.dumps(stage.next_stages), json.dumps(stage.next_stage_ids),
            json.dumps(stage.after_stages_finished), json.dumps(stage.clear_files), json.dumps(stage.lib_replacement_necessary), 
            json.dumps(stage.lib_mapping), json.dumps(stage.processing_steps), stage.execute_remote, stage.run_immediate
        ))
        stage_db_id = c.lastrowid

        conn.commit()

        for action in stage.actions:
            actions_data.add_action(stage_id=stage_db_id, action=action)

        if stage_db_id is None:
            raise Exception(f"Failed to insert stage '{stage.name}' for meta_file_id {meta_file_id}.")
        stage.id = stage_db_id





def get_stages(meta_file_id: int, cursor: sqlite3.Cursor|None=None, steps: 'actions_data.Deployment_Steps|None'=None) -> s.Stage_List_list:
    """
    Args:
        cursor, steps: Loading a whole deployment: on its connection, with its steps loaded at once (meta_file_data)
    """

    if cursor is not None:
        stage_rows = cursor.execute("SELECT * FROM stages WHERE meta_file_id = ? ORDER BY id", (meta_file_id,)).fetchall()
    else:
        with app_sqlite.get_db_connection() as conn:
            stage_rows = conn.execute("SELECT * FROM stages WHERE meta_file_id = ? ORDER BY id", (meta_file_id,)).fetchall()

    stages = s.Stage_List_list()

    for row in stage_rows:
        stages.append(_convert_row_to_stage(row, steps))

    return stages




def get_stage(stage_id: int) -> s.Stage | None:

    with app_sqlite.get_db_connection() as conn:

        c = conn.cursor()
        c.execute("SELECT * FROM stages WHERE id = ?", (stage_id,))
        row = c.fetchone()

    return _convert_row_to_stage(row) if row else None




def _convert_row_to_stage(row: sqlite3.Row, steps: 'actions_data.Deployment_Steps|None'=None) -> s.Stage:

    stage_dict = dict(row)
    stage_dict['next_stages'] = json.loads(stage_dict['next_stages']) if stage_dict['next_stages'] else []
    stage_dict['next_stage_ids'] = json.loads(stage_dict['next_stage_ids']) if stage_dict['next_stage_ids'] else []
    stage_dict['after_stages_finished'] = json.loads(stage_dict['after_stages_finished']) if stage_dict['after_stages_finished'] else []
    stage_dict['processing_steps'] = json.loads(stage_dict['processing_steps']) if stage_dict['processing_steps'] else []
    stage_dict['lib_mapping'] = json.loads(stage_dict['lib_mapping']) if stage_dict['lib_mapping'] else {}
    stage_dict['status'] = Stage_Status(stage_dict['status'])
    stage_dict['run_immediate'] = stage_dict['run_immediate'] if 'run_immediate' in stage_dict else False
    stage_dict['actions'] = steps.of_stage(row['id']) if steps is not None else actions_data.get_actions(stage_id=row['id'])

    stage_obj = s.Stage(dict=stage_dict)
    stage_obj.saved_values = _get_values(stage_obj)

    return stage_obj




def _get_values(stage: s.Stage) -> dict:
    """Columns which can change after the stage has been created. Not the status (and its time): only a transition changes it."""

    return {
        'next_stages': json.dumps(stage.next_stages),
        'next_stage_ids': json.dumps(stage.next_stage_ids),
        'after_stages_finished': json.dumps(stage.after_stages_finished),
        'lib_mapping': json.dumps(stage.lib_mapping),
    }




def refresh_stages(stages: s.Stage_List_list, meta_file_id: int) -> None:
    """Takes over status and next stages from the database, they may have been changed by another run of this deployment"""

    with app_sqlite.get_db_connection() as conn:
        rows = conn.execute("SELECT id, status, next_stage_ids, update_time FROM stages WHERE meta_file_id = ?", (meta_file_id,)).fetchall()

    current = {row['id']: row for row in rows}

    for stage in stages:

        if stage.id not in current:
            continue

        row = current[stage.id]
        stage.status = Stage_Status(row['status'])
        stage.next_stage_ids = json.loads(row['next_stage_ids']) if row['next_stage_ids'] else []
        stage.update_time = datetime.datetime.fromisoformat(row['update_time'])
        stage.saved_values = _get_values(stage)




def transition(stage_id: int, to: Stage_Status) -> tuple[bool, Stage_Status|None]:
    """
    Changes the status of a stage, if the change is allowed from its current status in the database (modules/state.py).

    Returns:
        (changed, status): the status in the database afterwards (None if the stage doesn't exist)
    """

    allowed = state.allowed_from(state.STAGE, to)

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        c.execute(f"UPDATE stages SET status = ?, update_time = ? WHERE id = ? AND status IN ({', '.join('?' * len(allowed))})",
                  (to.value, datetime.datetime.now(), stage_id, *allowed))
        conn.commit()

        if c.rowcount == 1:
            return True, to

        row = c.execute("SELECT status FROM stages WHERE id = ?", (stage_id,)).fetchone()
        return False, Stage_Status(row['status']) if row else None




def claim_stage(stage_id: int, exclusive: bool) -> bool:
    """
    Sets a stage which can be run to status `in process`. A stage can only be claimed once, even by multiple processes.

    Args:
        exclusive (bool): No other stage of the deployment may be in process

    Returns:
        bool: False if the stage can't be run (anymore)
    """

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE stages SET status = ?, update_time = ?
            WHERE id = ? AND status IN (?, ?)
              AND (? = 0 OR NOT EXISTS (SELECT 1 FROM stages other
                                         WHERE other.meta_file_id = stages.meta_file_id AND other.id <> stages.id
                                           AND other.status IN (?, ?, ?)))
        ''', (
            Stage_Status.IN_PROCESS.value, datetime.datetime.now(), stage_id, Stage_Status.READY.value, Stage_Status.FAILED.value,
            exclusive, Stage_Status.IN_PROCESS.value, Stage_Status.IN_PREPERATION.value, Stage_Status.PREPARE.value
        ))
        conn.commit()
        return c.rowcount == 1




def activate_stage(stage_id: int, wait_for: list[str]|None=None) -> bool:
    """
    Sets a stage which has not been reached yet to status `ready`.
    Parallel branches which lead to the same stage can do this at the same time.

    Args:
        wait_for: names of stages of the same deployment which have to be finished before (`after_stages_finished`).
                  They are checked in the same statement: of several branches which finish at the same time,
                  the last one activates the stage.

    Returns:
        bool: False if the stage has been reached already, or still waits for other stages
    """

    sql = "UPDATE stages SET status = ?, update_time = ? WHERE id = ? AND status = ?"
    params: list = [Stage_Status.READY.value, datetime.datetime.now(), stage_id, Stage_Status.NEW.value]

    names = sorted(set(wait_for or []))
    if names:
        sql += f""" AND (SELECT COUNT(DISTINCT waited.name) FROM stages waited
                         WHERE waited.meta_file_id = stages.meta_file_id AND waited.status = ?
                           AND waited.name IN ({', '.join('?' * len(names))})) = ?"""
        params += [Stage_Status.FINISHED.value, *names, len(names)]

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        c.execute(sql, params)
        conn.commit()
        return c.rowcount == 1



def save_stages(stages: s.Stage_List_list, cursor: sqlite3.Cursor=None, meta_dir: str|None=None):
    
    for stage in stages:
        save_stage(stage, cursor, meta_dir)


def save_stage(stage: s.Stage, cursor: sqlite3.Cursor=None, meta_dir: str|None=None):

    if cursor is not None:
        _save_stage(stage, cursor, meta_dir)
        return

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        _save_stage(stage, c, meta_dir)
        
        conn.commit()




def _save_stage(stage: s.Stage, cursor: sqlite3.Cursor, meta_dir: str|None=None):

    stage.saved_values = app_sqlite.update_changes(cursor, 'stages', stage.id, _get_values(stage), stage.saved_values)

    for action in stage.actions:
        actions_data.save_action(action, cursor, stage_id=stage.id, meta_dir=meta_dir)
