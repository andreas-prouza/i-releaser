from io import StringIO
import sqlite3
import json
import logging
from modules.db import  app_sqlite
from modules import meta_file as mf
from modules import stages as s
from modules import workflow as wf
from modules import meta_file_history as mfh
from modules import deploy_version as dv
from modules.meta_file_status import Meta_file_status
from modules.db import stage_data, deploy_object_data





def create_new_meta_file(workflow_name: str, object_list: str|None=None, custom_data: dict={}) -> 'Meta_File':
    """Creates a new Meta_File instance and saves it to the database."""
    workflow: wf.Workflow = wf.Workflow(name=workflow_name)

    wf_s = workflow.stages
    #s.Stage.get_stage_from_workflow
    deploy_version = dv.Deploy_Version.get_next_deploy_version(project=workflow.default_project, status=Meta_file_status.NEW)

    meta_file = mf.Meta_File(
        project=workflow.default_project,
        workflow_name=workflow_name,
        workflow=workflow.get_dict(),
        object_list=object_list,
        custom_data=custom_data,
        deploy_version_id=deploy_version['id'], 
        deploy_version=deploy_version['version']
    )

    add_meta_file(meta_file)
    meta_file.activate_history()

    for stage_dict in workflow.stages:
        new_stage: s.Stage = stage_data.create_stage(meta_file_id=meta_file.id, name=stage_dict['name'], workflow=workflow)
        meta_file.stages.append(new_stage)

    #meta_file.stages = s.Stage_List_list.generate_stages(meta_file)
    meta_file.stages.get_stages_by_name('START')[0].status = s.Stage_Status.READY

    return meta_file
    



def _load_workflow_definition(c: sqlite3.Cursor, meta_file_id: int) -> wf.Workflow | None:
    c.execute("SELECT * FROM workflow_definitions WHERE meta_file_id = ?", (meta_file_id,))
    workflow_row = c.fetchone()
    return wf.Workflow(dict=json.loads(workflow_row['definition'])) if workflow_row else None




def _load_run_history(c: sqlite3.Cursor, meta_file_id: int) -> mfh.Meta_File_History_List_list:

    c.execute("SELECT * FROM run_history WHERE meta_file_id = ?", (meta_file_id,))
    run_history_rows = c.fetchall()
    run_history = mfh.Meta_File_History_List_list()

    for row in run_history_rows:
        
        if row['log'] is None or len(row['log']) == 0:
            c.execute("DELETE FROM run_history WHERE id = ?", (row['id'],))
            c.connection.commit()
            continue

        run_history.add_history(mfh.Meta_File_History(id=row['id'], meta_file_id=row['meta_file_id'], create_time=row['create_time'], log=row['log']))

    return run_history




def get_meta_file_by_id(meta_file_id: int) -> mf.Meta_File | None:
    """
    Loads a Meta_File object from the SQLite database by its ID.
    """
    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""SELECT mf.*, dv.version as deploy_version 
                   FROM meta_files mf left join deploy_versions dv on mf.deploy_version_id = dv.id
                   WHERE mf.id = ?""", (meta_file_id,))
        meta_file_row = c.fetchone()

        if not meta_file_row:
            return None
    return _convert_meta_file_row_to_object(c, meta_file_row)



def get_meta_file(project: str, version: int) -> mf.Meta_File | None:
    """
    Loads a Meta_File object from the SQLite database.
    """
    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""SELECT mf.*, dv.version as deploy_version 
                   FROM meta_files mf left join deploy_versions dv on mf.deploy_version_id = dv.id 
                   WHERE mf.project = ? AND dv.version = ?""", (project, version))
        meta_file_row = c.fetchone()

        if not meta_file_row:
            return None
    return _convert_meta_file_row_to_object(c, meta_file_row)
    


def _convert_meta_file_row_to_object(c: sqlite3.Cursor, meta_file_row: sqlite3.Row) -> mf.Meta_File:

    meta_file_id = meta_file_row['id']

    workflow = _load_workflow_definition(c, meta_file_id)
    deploy_objects = deploy_object_data.get_deploy_objects(meta_file_id)
    stages = stage_data.get_stages(meta_file_id)
    run_history = _load_run_history(c, meta_file_id)

    meta_file = mf.Meta_File(
        id=meta_file_id,
        project=meta_file_row['project'],
        meta_dir=meta_file_row['meta_dir'],
        workflow_name=workflow.name if workflow else None,
        workflow=workflow.get_dict() if workflow else None,
        object_list=meta_file_row['object_list'],
        create_time=meta_file_row['create_time'],
        update_time=meta_file_row['update_time'],
        status=mf.Meta_file_status(meta_file_row['status']),
        deploy_version=meta_file_row['deploy_version'],
        deploy_version_id=meta_file_row['deploy_version_id'],
        stages=stages,
        custom_data=json.loads(meta_file_row['custom_data'])
    )
    meta_file.deploy_objects = deploy_objects
    meta_file.run_history = run_history
    meta_file.commit = meta_file_row['commit_hash']
    meta_file.release_branch = meta_file_row['release_branch']
    meta_file.main_deploy_lib = meta_file_row['main_lib']
    meta_file.backup_deploy_lib = meta_file_row['backup_lib']
    meta_file.remote_deploy_lib = meta_file_row['remote_lib']
    meta_file.activate_history()

    return meta_file



def _save_workflow_definition(c: sqlite3.Cursor, meta_file_id: int, workflow: wf.Workflow):
    if workflow:
        c.execute("SELECT id FROM workflow_definitions WHERE meta_file_id = ?", (meta_file_id,))
        if c.fetchone():
            c.execute("UPDATE workflow_definitions SET definition = ? WHERE meta_file_id = ?",
                      (json.dumps(workflow.get_dict()), meta_file_id))
        else:
            c.execute("INSERT INTO workflow_definitions (meta_file_id, definition) VALUES (?, ?)",
                      (meta_file_id, json.dumps(workflow.get_dict())))






def _save_run_history(c: sqlite3.Cursor, run_history: mfh.Meta_File_History_List_list):
    
    for history in run_history:
        log = history.log
        if type(log) == StringIO:
            log = log.getvalue()

        if len(log) == 0:
            c.execute("DELETE FROM run_history WHERE id = ?", (history.id,))
        else:
            c.execute("UPDATE run_history SET log = ? WHERE id = ?",
                    (log, history.id))
        


def save_meta_file(meta_file: mf.Meta_File):
    """
    Saves a Meta_File object and all its related data to the SQLite database.
    This function handles inserting or updating records across multiple tables.
    """
    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()

        c.execute('''
            UPDATE meta_files 
            SET commit_hash = ?, release_branch = ?, create_time = ?, update_time = ?, status = ?, 
                object_list = ?, main_lib = ?, remote_lib = ?, backup_lib = ?, custom_data = ?
            WHERE id = ?
        ''', (
            meta_file.commit, meta_file.release_branch, meta_file.create_time, meta_file.update_time,
            meta_file.status.value, meta_file.object_list, meta_file.main_deploy_lib,
            meta_file.remote_deploy_lib, meta_file.backup_deploy_lib, json.dumps(meta_file.custom_data),
            meta_file.id
        ))

        deploy_object_data.save_deploy_objects(meta_file.deploy_objects, c)
        stage_data.save_stages(meta_file.stages, c)
        _save_run_history(c, meta_file.run_history)
        _save_workflow_definition(c, meta_file.id, meta_file.workflow)

        conn.commit()
    logging.info(f"Meta file for project {meta_file.project} version {meta_file.deploy_version} saved to database.")



def add_meta_file(meta_file: mf.Meta_File):
    """
    Saves a Meta_File object and all its related data to the SQLite database.
    This function handles inserting or updating records across multiple tables.
    """
    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()

        c.execute('''
            INSERT INTO meta_files (project, deploy_version_id, commit_hash, release_branch, create_time, 
                                    meta_dir,
                                    update_time, status, object_list, custom_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            meta_file.project, meta_file.deploy_version_id, meta_file.commit, meta_file.release_branch,
            meta_file.create_time, meta_file.meta_dir, meta_file.update_time, meta_file.status.value,
            meta_file.object_list, json.dumps(meta_file.custom_data)
        ))
        meta_file.id = c.lastrowid
        meta_file.set_libs()

        _save_workflow_definition(c, meta_file.id, meta_file.workflow)

        conn.commit()
    logging.info(f"Meta file for project {meta_file.project} version {meta_file.deploy_version} saved to database.")
