import json, logging
import sqlite3
from modules.db import actions_data, app_sqlite
from modules import deploy_object as do


def create_deploy_object(meta_file_id: int, level: int|None=None, lib: str|None=None, prod_lib: str|None=None, name: str|None=None, type: str|None=None, attribute: str|None=None, source: str|None=None, source_only: bool=False, object: do.Deploy_Object|None=None) -> do.Deploy_Object:

    deploy_object: do.Deploy_Object = object or do.Deploy_Object(level=level, lib=lib, prod_lib=prod_lib, name=name, type=type, attribute=attribute, source=source, source_only=source_only)
    deploy_object.meta_file_id = meta_file_id
    
    _add_deploy_object(meta_file_id=meta_file_id, deploy_object=deploy_object)

    return deploy_object



def _add_deploy_object(meta_file_id: int, deploy_object: do.Deploy_Object):
    """
    Adds a deploy object to the database for the given meta_file_id.

    Args:
        c (sqlite3.Cursor, optional): Database cursor. If not provided, a new connection will be used.
        meta_file_id (int): ID of the meta file.
        deploy_object (do.Deploy_Object): Deploy object to be added.
    """
    with app_sqlite.get_db_connection() as conn:

        c = conn.cursor()
        c.execute('''
            INSERT INTO deploy_objects (meta_file_id, level, prod_lib, lib, name, type, attribute, deploy_status, ready, source, source_only, properties)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            meta_file_id, deploy_object.level, deploy_object.prod_lib, deploy_object.lib, deploy_object.name, deploy_object.type,
            deploy_object.attribute, deploy_object.deploy_status.value, deploy_object.ready, deploy_object.source, deploy_object.source_only, json.dumps(deploy_object.properties)
        ))

        deploy_object_db_id = c.lastrowid
        deploy_object.id = deploy_object_db_id

        conn.commit()

        if deploy_object_db_id is None:
            raise Exception(f"Failed to insert deploy object '{deploy_object.name}' for meta_file_id {meta_file_id}.")






def get_deploy_objects(meta_file_id: int) -> do.Deploy_Object_List:

    logging.debug(f"Fetching deploy objects for meta_file_id: {meta_file_id}")

    with app_sqlite.get_db_connection() as conn:

        c = conn.cursor()
        c.execute("SELECT * FROM deploy_objects WHERE meta_file_id = ? order by level", (meta_file_id,))
        object_rows = c.fetchall()
        objects: do.Deploy_Object_List = do.Deploy_Object_List()
        
        for row in object_rows:
            object_obj: do.Deploy_Object = _convert_deploy_object_row_to_dict(row)
            objects.append(object_obj)
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




def get_deploy_object_list(filters: dict|None=None) -> list[dict]:

    object_obj: list[dict] = []
    
    with app_sqlite.get_db_connection() as conn:

        c = conn.cursor()
        where = ""
        params = []
        if filters:
            for key, value in filters.items():
                where += f" AND {key} = ?"
                params.append(value)

        sql = f"""SELECT  mf.project, do.prod_lib, do.name, do.type, do.attribute, DATETIME(max(mf.create_time)) latest_create_time, count(*) as count
                      FROM deploy_objects do
                      left join meta_files mf on do.meta_file_id = mf.id
                  where 1=1 {where} 
                  group by mf.project, do.prod_lib, do.name, do.type, do.attribute
                  order by 6 desc 
                  limit 1000"""

        c.execute(sql, params)
        object_rows = c.fetchall()

        for row in object_rows:
            object_obj.append(dict(row))

    return object_obj



def get_deploy_object_lifecycle(project: str, prod_lib: str, name: str, type: str, attribute: str) -> list[dict]:

    object_obj: list[dict] = []
    
    with app_sqlite.get_db_connection() as conn:

        c = conn.cursor()
        c.execute("""SELECT do.meta_file_id, mf.project, do.prod_lib, do.lib, DATETIME(mf.create_time) as deployment_date, do.deploy_status as object_status, mf.status as deployment, do.source
                      FROM deploy_objects do
                      left join meta_files mf on do.meta_file_id = mf.id
                  where mf.project = ? AND do.prod_lib = ? AND do.name = ? AND do.type = ? AND do.attribute = ? 
                  order by do.meta_file_id desc""", [project, prod_lib, name, type, attribute])
        object_rows = c.fetchall()

        for row in object_rows:
            object_obj.append(dict(row))

    return object_obj




def _convert_deploy_object_row_to_dict(row: sqlite3.Row) -> do.Deploy_Object:
    object_dict = dict(row)
    object_dict['deploy_status'] = do.Obj_Status(object_dict['deploy_status'])
    object_dict['depends_on'] = json.loads(object_dict['depends_on'])
    object_dict['properties'] = json.loads(object_dict['properties']) if object_dict['properties'] else {}
    object_dict['source'] = object_dict['source']
    object_dict['source_only'] = object_dict['source_only']
    object_obj: do.Deploy_Object = do.Deploy_Object(dict_data=object_dict)
    object_obj.actions = actions_data.get_actions(deploy_object_id=object_obj.id)
    logging.debug(f"Select deploy object {object_obj.get_dict()=}")
    return object_obj



def save_deploy_objects(deploy_objects: list[do.Deploy_Object], cursor: sqlite3.Cursor|None=None):
    for deploy_object in deploy_objects:
        save_deploy_object(deploy_object, cursor)


def save_deploy_object(deploy_object: do.Deploy_Object, cursor: sqlite3.Cursor|None=None):
    if cursor is not None:
        _save_deploy_object(deploy_object, cursor)
        return

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        _save_deploy_object(deploy_object, c)
        conn.commit()


def _save_deploy_object(deploy_object: do.Deploy_Object, cursor: sqlite3.Cursor):
    cursor.execute('''
        UPDATE deploy_objects 
        SET level = ?, prod_lib = ?, lib = ?, name = ?, type = ?, attribute = ?, deploy_status = ?, ready = ?, depends_on = ?, source = ?, source_only = ?, properties = ?
        WHERE id = ?
    ''', (
        deploy_object.level, deploy_object.prod_lib, deploy_object.lib, deploy_object.name, deploy_object.type,
        deploy_object.attribute, deploy_object.deploy_status.value, deploy_object.ready,
        json.dumps(deploy_object.depends_on.get_objects_as_list_of_dict()), deploy_object.source, deploy_object.source_only, json.dumps(deploy_object.properties),
        deploy_object.id
    ))
    logging.debug(f"Saved deploy object {deploy_object.get_dict()=}")

    for action in deploy_object.actions:
        actions_data.save_action(action, cursor, deploy_object_id=deploy_object.id)


