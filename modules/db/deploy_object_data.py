import sqlite3
from modules.db import actions_data, app_sqlite
from modules import deploy_object as do


def create_deploy_object(meta_file_id: int, level: int, lib: str, prod_lib: str, name: str, type: str, attribute: str) -> do.Deploy_Object:
    
    deploy_object: do.Deploy_Object = do.Deploy_Object(level=level, lib=lib, prod_lib=prod_lib, name=name, type=type, attribute=attribute)
    deploy_object.meta_file_id = meta_file_id
    
    _add_deploy_object(meta_file_id=meta_file_id, deploy_object=deploy_object)

    return deploy_object



def _add_deploy_object(meta_file_id: int, deploy_object: do.Deploy_Object):
    """
    Adds a deploy object to the database for the given meta_file_id.

    Args:
        c (sqlite3.Cursor): Database cursor.
        meta_file_id (int): ID of the meta file.
        deploy_object (do.Deploy_Object): Deploy object to be added.
    """
    with app_sqlite.get_db_connection() as conn:

        c = conn.cursor()
        c.execute('''
            INSERT INTO deploy_objects (meta_file_id, level, prod_lib, lib, name, type, attribute, deploy_status, ready)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            meta_file_id, deploy_object.level, deploy_object.prod_lib, deploy_object.lib, deploy_object.name, deploy_object.type,
            deploy_object.attribute, deploy_object.deploy_status.value, deploy_object.ready
        ))

        deploy_object_db_id = c.lastrowid
        deploy_object.id = deploy_object_db_id

        conn.commit()

        if deploy_object_db_id is None:
            raise Exception(f"Failed to insert deploy object '{deploy_object.name}' for meta_file_id {meta_file_id}.")






def get_deploy_objects(meta_file_id: int) -> do.Deploy_Object_List:

    with app_sqlite.get_db_connection() as conn:

        c = conn.cursor()
        c.execute("SELECT * FROM deploy_objects WHERE meta_file_id = ? order by level", (meta_file_id,))
        object_rows = c.fetchall()
        objects: do.Deploy_Object_List = do.Deploy_Object_List()
        
        for row in object_rows:
            object_dict = dict(row)
            object_dict['deploy_status'] = do.Obj_Status(object_dict['deploy_status'])
            
            object_obj: do.Deploy_Object = do.Deploy_Object(dict=object_dict)
            object_obj.actions = actions_data.get_actions(deploy_object_id=object_obj.id)
            objects.append(object_obj)
    return objects




def get_deploy_object(deploy_object_id: int) -> do.Deploy_Object | None:

    object_obj: do.Deploy_Object|None = None
    
    with app_sqlite.get_db_connection() as conn:

        c = conn.cursor()
        c.execute("SELECT * FROM deploy_objects WHERE id = ?", (deploy_object_id,))
        object_rows = c.fetchall()
        
        row = object_rows[0] if object_rows else None
        if row is None:
            return None
        object_dict = dict(row)
        object_dict['deploy_status'] = do.Obj_Status(object_dict['deploy_status'])
        object_obj = do.Deploy_Object(dict=object_dict)
        object_obj.actions = actions_data.get_actions(deploy_object_id=object_obj.id)

    return object_obj




def save_deploy_objects(deploy_objects: list[do.Deploy_Object], cursor: sqlite3.Cursor=None):
    for deploy_object in deploy_objects:
        save_deploy_object(deploy_object, cursor)


def save_deploy_object(deploy_object: do.Deploy_Object, cursor: sqlite3.Cursor=None):
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
        SET level = ?, prod_lib = ?, lib = ?, name = ?, type = ?, attribute = ?, deploy_status = ?, ready = ?
        WHERE id = ?
    ''', (
        deploy_object.level, deploy_object.prod_lib, deploy_object.lib, deploy_object.name, deploy_object.type,
        deploy_object.attribute, deploy_object.deploy_status.value, deploy_object.ready,
        deploy_object.id
    ))

    for action in deploy_object.actions:
        actions_data.save_action(action, cursor, deploy_object_id=deploy_object.id)


