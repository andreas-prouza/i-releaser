from __future__ import annotations

import os
from io import StringIO
import sqlite3
import json
import logging
from modules.db import  app_sqlite, compression
from modules import meta_file as mf
from modules import stages as s
from modules import workflow as wf
from modules import meta_file_history as mfh
from modules import deploy_version as dv
from modules import errors, files, hooks
from modules.meta_file_status import Meta_file_status
from modules.db import stage_data, deploy_object_data, processing_job_data





def create_new_meta_file(workflow_name: str, object_list: str|None=None, custom_data: dict|None=None) -> 'Meta_File':
    """Creates a new Meta_File instance and saves it to the database."""
    workflow: wf.Workflow = wf.Workflow(name=workflow_name)
    workflow.check_custom_data(custom_data)

    if object_list is not None:
        workflow.check_object_list(object_list)

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
        deploy_version=deploy_version['version'],
        parallel_deployment_execution_allowed=workflow.parallel_deployment_execution_allowed,
    )

    add_meta_file(meta_file)
    meta_file.activate_history()

    try:
        for stage_dict in workflow.stages:
            new_stage: s.Stage = stage_data.create_stage(meta_file_id=meta_file.id, name=stage_dict['name'], workflow=workflow)
            meta_file.stages.append(new_stage)

        #meta_file.stages = s.Stage_List_list.generate_stages(meta_file)
        meta_file.stages.get_stages_by_name('START')[0].status = s.Stage_Status.READY
    finally:
        meta_file.deactivate_history()

    hooks.emit(hooks.Event.DEPLOYMENT_CREATED, meta_file)

    return meta_file
    



def _load_workflow_definition(c: sqlite3.Cursor, meta_file_id: int) -> wf.Workflow | None:
    c.execute("SELECT * FROM workflow_definitions WHERE meta_file_id = ?", (meta_file_id,))
    workflow_row = c.fetchone()
    return wf.Workflow(dict=json.loads(compression.decompress_field(workflow_row['definition']))) if workflow_row else None



def get_meta_dir(cursor: sqlite3.Cursor, meta_file_id: int|None=None, stage_id: int|None=None, deploy_object_id: int|None=None, action_id: int|None=None) -> str | None:
    sql = "SELECT meta_dir FROM meta_files WHERE "
    param = ()

    if stage_id is not None:
        sql += " id in (SELECT meta_file_id FROM stages WHERE id = ?)"
        param = (stage_id,)
    elif deploy_object_id is not None:
        sql += " id in (SELECT meta_file_id FROM deploy_objects WHERE id = ?)"
        param = (deploy_object_id,)
    elif action_id is not None:
        sql += " id in (select COALESCE(s.meta_file_id, do.meta_file_id, s2.meta_file_id, do2.meta_file_id ) \
                        from actions a \
                            left join stages s on s.id = a.stage_id \
                            left join deploy_objects do on do.id = a.deploy_object_id \
                            left join actions a2 on a2.id = a.action_id \
                            left join stages s2 on s2.id = a2.stage_id \
                            left join deploy_objects do2 on do2.id = a2.deploy_object_id \
                        WHERE a.id = ?)"
        param = (action_id,)
    elif meta_file_id is not None:
        sql += "id = ?"
        param = (meta_file_id,)
    else:
        raise Exception("Either meta_file_id, stage_id, deploy_object_id, or action_id must be provided.")

    cursor.execute(sql, param)
    meta_file_row = cursor.fetchone()
    return meta_file_row['meta_dir'] if meta_file_row else None




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
        custom_data=json.loads(compression.decompress_field(meta_file_row['custom_data'])) if meta_file_row['custom_data'] else None,
        parallel_deployment_execution_allowed=meta_file_row['parallel_deployment_execution_allowed']
    )
    meta_file.deploy_objects = deploy_objects
    meta_file.run_history = run_history
    meta_file.processing_jobs = processing_job_data.get_active_jobs(meta_file_id)
    meta_file.commit = meta_file_row['commit_hash']
    meta_file.release_branch = meta_file_row['release_branch']
    meta_file.main_deploy_lib = meta_file_row['main_lib']
    meta_file.backup_deploy_lib = meta_file_row['backup_lib']
    meta_file.remote_deploy_lib = meta_file_row['remote_lib']
    meta_file.saved_values = _get_values(meta_file)

    return meta_file



def _get_values(meta_file: mf.Meta_File) -> dict:
    return {
        'commit_hash': meta_file.commit,
        'release_branch': meta_file.release_branch,
        'create_time': meta_file.create_time,
        'update_time': meta_file.update_time,
        'status': meta_file.status.value,
        'object_list': meta_file.object_list,
        'main_lib': meta_file.main_deploy_lib,
        'remote_lib': meta_file.remote_deploy_lib,
        'backup_lib': meta_file.backup_deploy_lib,
        'custom_data': compression.compress_field(json.dumps(meta_file.custom_data)) if meta_file.custom_data else None,
    }



def get_status(meta_file_id: int) -> Meta_file_status|None:

    with app_sqlite.get_db_connection() as conn:
        row = conn.execute("SELECT status FROM meta_files WHERE id = ?", (meta_file_id,)).fetchone()

    return Meta_file_status(row['status']) if row else None



def claim_finished(meta_file_id: int) -> bool:
    """
    Sets a deployment to status `finished`. Parallel stages can finish at the same time, only one of them succeeds.

    Returns:
        bool: False if the deployment has been finished or canceled already
    """

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE meta_files SET status = ? WHERE id = ? AND status NOT IN (?, ?)",
                  (Meta_file_status.FINISHED.value, meta_file_id, Meta_file_status.FINISHED.value, Meta_file_status.CANCELED.value))
        conn.commit()
        return c.rowcount == 1



def change_custom_data(meta_file_id: int, change) -> dict:
    """
    Changes the current custom data of a deployment, not the one of a copy which may be outdated.

    Args:
        change: Function which gets the custom data and returns the changed custom data

    Returns:
        dict: The changed custom data
    """

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")

        row = c.execute("SELECT custom_data FROM meta_files WHERE id = ?", (meta_file_id,)).fetchone()
        custom_data = change(json.loads(compression.decompress_field(row['custom_data'])) if row['custom_data'] else {})

        c.execute("UPDATE meta_files SET custom_data = ? WHERE id = ?",
                  (compression.compress_field(json.dumps(custom_data)) if custom_data else None, meta_file_id))
        conn.commit()

    return custom_data



def get_meta_file_id_of_action_run(run_id: int) -> int|None:
    """Deployment of an entry in the run history of a step"""

    with app_sqlite.get_db_connection() as conn:
        row = conn.execute("""
            SELECT COALESCE(s.meta_file_id, do.meta_file_id, s2.meta_file_id, do2.meta_file_id) AS meta_file_id
              FROM action_run_history arh
              INNER JOIN actions a ON a.id = arh.action_id
              LEFT JOIN stages s ON s.id = a.stage_id
              LEFT JOIN deploy_objects do ON do.id = a.deploy_object_id
              LEFT JOIN actions a2 ON a2.id = a.action_id
              LEFT JOIN stages s2 ON s2.id = a2.stage_id
              LEFT JOIN deploy_objects do2 ON do2.id = a2.deploy_object_id
             WHERE arh.id = ?""", (run_id,)).fetchone()

    return row['meta_file_id'] if row else None



def get_meta_file_id_of_run(run_id: int) -> int|None:
    """Deployment of an entry in its run history"""

    with app_sqlite.get_db_connection() as conn:
        row = conn.execute("SELECT meta_file_id FROM run_history WHERE id = ?", (run_id,)).fetchone()

    return row['meta_file_id'] if row else None



def get_workflow_name(meta_file_id: int) -> str|None:

    with app_sqlite.get_db_connection() as conn:
        row = conn.execute("SELECT name FROM workflow_definitions WHERE meta_file_id = ?", (meta_file_id,)).fetchone()

    return row['name'] if row else None



def get_workflow_names() -> list[str]:
    """Names of all workflows which have deployments"""

    with app_sqlite.get_db_connection() as conn:
        rows = conn.execute("SELECT DISTINCT name FROM workflow_definitions").fetchall()

    return [row['name'] for row in rows]



def get_state_marker(meta_file_id: int) -> tuple|None:
    """
    Small value which changes whenever the deployment changes, with its steps, objects and jobs.
    So a page which watches a deployment doesn't need to load all of it to find out.
    """

    with app_sqlite.get_db_connection() as conn:
        meta_file_row = conn.execute("SELECT status, update_time FROM meta_files WHERE id = ?", (meta_file_id,)).fetchone()

        if meta_file_row is None:
            return None

        stages_row = conn.execute("SELECT group_concat(status), max(update_time) FROM stages WHERE meta_file_id = ?", (meta_file_id,)).fetchone()
        jobs_row = conn.execute("SELECT count(*), group_concat(status), max(id) FROM processing_jobs WHERE meta_file_id = ?", (meta_file_id,)).fetchone()

    return (*meta_file_row, *stages_row, *jobs_row)



def _save_workflow_definition(c: sqlite3.Cursor, meta_file_id: int, workflow: wf.Workflow):
    if workflow:
        c.execute("SELECT id FROM workflow_definitions WHERE meta_file_id = ?", (meta_file_id,))
        if c.fetchone():
            c.execute("UPDATE workflow_definitions SET name = ?, default_project = ?, definition = ? WHERE meta_file_id = ?",
                      (workflow.name, workflow.default_project, compression.compress_field(json.dumps(workflow.get_dict())) , meta_file_id))
        else:
            c.execute("INSERT INTO workflow_definitions (meta_file_id, name, default_project, definition) VALUES (?, ?, ?, ?)",
                      (meta_file_id, workflow.name, workflow.default_project, compression.compress_field(json.dumps(workflow.get_dict()))))






def _save_run_history(c: sqlite3.Cursor, run_history: mfh.Meta_File_History_List_list, meta_dir: str):
    
    for history in run_history:
        log = history.log
        if type(log) == StringIO:
            log = log.getvalue()

        # Already stored in its log file
        if log is None or log[:7] == "file://":
            continue

        if len(log) == 0:
            c.execute("DELETE FROM run_history WHERE id = ?", (history.id,))

        log_file_path = os.path.join(meta_dir, "logs", "run_history", f"{history.id}.log")
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        files.writeText(log, log_file_path)
        c.execute("UPDATE run_history SET log = ? WHERE id = ?",
                  (f"file://{log_file_path}", history.id))



def save_meta_file(meta_file: mf.Meta_File):
    """
    Saves what has changed in this Meta_File object to the SQLite database.
    Only changed columns are written, so a stage doesn't overwrite what another stage or a user has done meanwhile.
    """
    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()

        meta_file.saved_values = app_sqlite.update_changes(c, 'meta_files', meta_file.id, _get_values(meta_file), meta_file.saved_values)

        deploy_object_data.save_deploy_objects(meta_file.deploy_objects, c, meta_dir=meta_file.meta_dir)
        stage_data.save_stages(meta_file.stages, c, meta_dir=meta_file.meta_dir)
        _save_run_history(c, meta_file.run_history, meta_file.meta_dir)

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
                                    update_time, status, object_list, custom_data, parallel_deployment_execution_allowed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            meta_file.project, meta_file.deploy_version_id, meta_file.commit, meta_file.release_branch,
            meta_file.create_time, meta_file.meta_dir, meta_file.update_time, meta_file.status.value,
            meta_file.object_list, compression.compress_field(json.dumps(meta_file.custom_data)) if meta_file.custom_data else None, meta_file.parallel_deployment_execution_allowed
        ))
        meta_file.id = c.lastrowid
        meta_file.set_libs()

        _save_workflow_definition(c, meta_file.id, meta_file.workflow)

        conn.commit()

    # All columns are new
    meta_file.saved_values = None
    logging.info(f"Meta file for project {meta_file.project} version {meta_file.deploy_version} saved to database.")
