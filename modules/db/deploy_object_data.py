import json, logging
import sqlite3
from modules.db import actions_data, app_sqlite
from modules import deploy_object as do


def create_deploy_object(meta_file_id: int, level: int|None=None, lib: str|None=None, prod_lib: str|None=None, name: str|None=None, type: str|None=None, attribute: str|None=None, source: str|None=None, source_only: bool=False, object: do.Deploy_Object|None=None) -> do.Deploy_Object:

    deploy_object: do.Deploy_Object = object or do.Deploy_Object(level=level, lib=lib, prod_lib=prod_lib, name=name, type=type, attribute=attribute, source=source, source_only=source_only)
    deploy_object.meta_file_id = meta_file_id
    
    _add_deploy_object(meta_file_id=meta_file_id, deploy_object=deploy_object)

    return deploy_object



def _insert_deploy_object(c: sqlite3.Cursor, meta_file_id: int, deploy_object: do.Deploy_Object) -> None:
    """Inserts the deploy object; its id is set. The snapshot (saved_values) is set by the caller after the commit."""

    c.execute('''
        INSERT INTO deploy_objects (meta_file_id, level, prod_lib, lib, name, type, attribute, deploy_status, ready, source, source_only, properties)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        meta_file_id, deploy_object.level, deploy_object.prod_lib, deploy_object.lib, deploy_object.name, deploy_object.type,
        deploy_object.attribute, deploy_object.deploy_status.value, deploy_object.ready, deploy_object.source, deploy_object.source_only, json.dumps(deploy_object.properties)
    ))

    if c.lastrowid is None:
        raise Exception(f"Failed to insert deploy object '{deploy_object.name}' for meta_file_id {meta_file_id}.")

    deploy_object.id = c.lastrowid
    deploy_object.meta_file_id = meta_file_id



def _add_deploy_object(meta_file_id: int, deploy_object: do.Deploy_Object):
    """Adds a deploy object to the database for the given meta_file_id."""

    with app_sqlite.get_db_connection() as conn:
        _insert_deploy_object(conn.cursor(), meta_file_id, deploy_object)
        conn.commit()

    deploy_object.saved_values = _get_values(deploy_object)



def _delete_deploy_objects(c: sqlite3.Cursor, meta_file_id: int) -> None:

    action_ids = "SELECT id FROM actions WHERE deploy_object_id IN (SELECT id FROM deploy_objects WHERE meta_file_id = ?)"
    sub_action_ids = f"SELECT id FROM actions WHERE action_id IN ({action_ids})"
    c.execute(f"DELETE FROM action_run_history WHERE action_id IN ({sub_action_ids})", (meta_file_id,))
    c.execute(f"DELETE FROM action_run_history WHERE action_id IN ({action_ids})", (meta_file_id,))
    c.execute(f"DELETE FROM actions WHERE action_id IN ({action_ids})", (meta_file_id,))
    c.execute("DELETE FROM actions WHERE deploy_object_id IN (SELECT id FROM deploy_objects WHERE meta_file_id = ?)", (meta_file_id,))
    c.execute("DELETE FROM deploy_objects WHERE meta_file_id = ?", (meta_file_id,))



def replace_deploy_objects(meta_file_id: int, objects: list[do.Deploy_Object]) -> None:
    """Replaces all deploy objects of a deployment (with their actions) in one transaction, e.g. to import the object list again.
    If it fails, the old objects stay."""

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        _delete_deploy_objects(c, meta_file_id)
        for deploy_object in objects:
            _insert_deploy_object(c, meta_file_id, deploy_object)
        conn.commit()

    for deploy_object in objects:
        deploy_object.saved_values = _get_values(deploy_object)






def get_deploy_objects(meta_file_id: int, cursor: sqlite3.Cursor|None=None, steps: 'actions_data.Deployment_Steps|None'=None) -> do.Deploy_Object_List:
    """
    Args:
        cursor, steps: Loading a whole deployment: on its connection, with its steps loaded at once (meta_file_data)
    """

    logging.debug(f"Fetching deploy objects for meta_file_id: {meta_file_id}")

    sql = "SELECT * FROM deploy_objects WHERE meta_file_id = ? ORDER BY level, id"

    if cursor is not None:
        object_rows = cursor.execute(sql, (meta_file_id,)).fetchall()
    else:
        with app_sqlite.get_db_connection() as conn:
            object_rows = conn.execute(sql, (meta_file_id,)).fetchall()

    objects: do.Deploy_Object_List = do.Deploy_Object_List()

    for row in object_rows:
        objects.append(_convert_deploy_object_row_to_dict(row, steps))

    return objects




def get_deploy_object(deploy_object_id: int) -> do.Deploy_Object | None:

    logging.debug(f"Fetching deploy object for deploy_object_id: {deploy_object_id}")

    object_obj: do.Deploy_Object|None = None
    
    with app_sqlite.get_db_connection() as conn:

        c = conn.cursor()
        c.execute("SELECT * FROM deploy_objects WHERE id = ?", (deploy_object_id,))
        object_rows = c.fetchall()
        
        row = object_rows[0] if object_rows else None
        if row is None:
            return None
        object_obj = _convert_deploy_object_row_to_dict(row)

    return object_obj




def delete_deploy_objects(meta_file_id: int) -> None:
    """Deletes all deploy objects of a deployment with their actions"""

    with app_sqlite.get_db_connection() as conn:
        _delete_deploy_objects(conn.cursor(), meta_file_id)
        conn.commit()




def get_deploy_object_lifecycle(project: str, prod_lib: str, name: str, type: str, attribute: str, workflows: list[str]|None=None) -> list[dict]:
    """
    Args:
        workflows (list, optional): Only deployments of these workflows
    """

    object_obj: list[dict] = []
    where = ""
    params = [project, prod_lib, name, type, attribute]

    if workflows is not None:
        where = f" AND do.meta_file_id IN (SELECT meta_file_id FROM workflow_definitions WHERE name IN ({', '.join('?' * len(workflows))}))"
        params += workflows
    
    with app_sqlite.get_db_connection() as conn:

        c = conn.cursor()
        c.execute(f"""SELECT do.meta_file_id, mf.project, do.prod_lib, do.lib, DATETIME(mf.create_time) as deployment_date, do.deploy_status as object_status, mf.status as deployment, do.source
                      FROM deploy_objects do
                      left join meta_files mf on do.meta_file_id = mf.id
                  where mf.project = ? AND do.prod_lib = ? AND do.name = ? AND do.type = ? AND do.attribute = ? {where}
                  order by do.meta_file_id desc""", params)
        object_rows = c.fetchall()

        for row in object_rows:
            object_obj.append(dict(row))

    return object_obj




def _convert_deploy_object_row_to_dict(row: sqlite3.Row, steps: 'actions_data.Deployment_Steps|None'=None) -> do.Deploy_Object:
    object_dict = dict(row)
    object_dict['deploy_status'] = do.Obj_Status(object_dict['deploy_status'])
    object_dict['depends_on'] = json.loads(object_dict['depends_on']) if object_dict['depends_on'] else do.Deploy_Object_List()
    object_dict['properties'] = json.loads(object_dict['properties']) if object_dict['properties'] else {}
    object_dict['source'] = object_dict['source']
    object_dict['source_only'] = object_dict['source_only']
    object_obj: do.Deploy_Object = do.Deploy_Object(dict_data=object_dict)
    object_obj.actions = steps.of_deploy_object(object_obj.id) if steps is not None else actions_data.get_actions(deploy_object_id=object_obj.id)
    object_obj.saved_values = _get_values(object_obj)
    logging.debug(f"Select deploy object {object_obj.id}: {object_obj.lib}/{object_obj.name} ({object_obj.type})")
    return object_obj



def save_deploy_objects(deploy_objects: list[do.Deploy_Object], cursor: sqlite3.Cursor|None=None, meta_dir: str|None=None):
    for deploy_object in deploy_objects:
        save_deploy_object(deploy_object, cursor, meta_dir)


def save_deploy_object(deploy_object: do.Deploy_Object, cursor: sqlite3.Cursor|None=None, meta_dir: str|None=None):
    if cursor is not None:
        _save_deploy_object(deploy_object, cursor, meta_dir)
        return

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        _save_deploy_object(deploy_object, c, meta_dir)
        conn.commit()


def _get_values(deploy_object: do.Deploy_Object) -> dict:
    return {
        'level': deploy_object.level,
        'prod_lib': deploy_object.prod_lib,
        'lib': deploy_object.lib,
        'name': deploy_object.name,
        'type': deploy_object.type,
        'attribute': deploy_object.attribute,
        'deploy_status': deploy_object.deploy_status.value,
        'ready': deploy_object.ready,
        'depends_on': json.dumps(deploy_object.depends_on.get_objects_as_list_of_dict()),
        'source': deploy_object.source,
        'source_only': deploy_object.source_only,
        'properties': json.dumps(deploy_object.properties),
    }



def _save_deploy_object(deploy_object: do.Deploy_Object, cursor: sqlite3.Cursor, meta_dir: str|None=None):

    deploy_object.saved_values = app_sqlite.update_changes(cursor, 'deploy_objects', deploy_object.id, _get_values(deploy_object), deploy_object.saved_values)
    logging.debug(f"Saved deploy object {deploy_object.id}: {deploy_object.lib}/{deploy_object.name} ({deploy_object.type})")

    for action in deploy_object.actions:
        actions_data.save_action(action, cursor, deploy_object_id=deploy_object.id, meta_dir=meta_dir)


