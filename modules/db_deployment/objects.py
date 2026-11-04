"""
Tables of a deployment which are deployed by the DB deployment, and their deploy objects

Configured in the custom data of a deployment:

    {"db_deployment": {"tables": [{"lib": "PRODLIB", "name": "ORDERS", "columns": {...}, ...}]}}

The deploy objects which are deployed this way get the property "db_deployment":
* prepared: built in the shadow library, replaced at the cut-over
* deployed: replaced at the cut-over. Other deployment steps have to skip them (see check_deploy_object).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import TYPE_CHECKING

from modules.db_deployment.connection import Db_Deployment_Exception
from modules.object_status import Status as Obj_Status

if TYPE_CHECKING:
  from modules.meta_file import Meta_File
  from modules.deploy_object import Deploy_Object


C_PROPERTY = 'db_deployment'
C_PREPARED = 'prepared'
C_DEPLOYED = 'deployed'

C_SYSTEM_NAME = re.compile(r'[A-Z$#@][A-Z0-9$#@_.]{0,9}')

C_TABLE_ATTRIBUTES = ('sqltable', 'pf')
C_DEPENDENT_ATTRIBUTES = ('sqlindex', 'lf')



def get_shadow_lib(meta_file: Meta_File) -> str:
  """Library for the new tables of a deployment, like the other libraries of a deployment (see Meta_File.set_libs)"""
  return f"S{str(meta_file.id).zfill(9)}"



def get_backup_lib(meta_file: Meta_File) -> str:
  """The old tables are moved into the backup library of the deployment"""
  return (meta_file.backup_deploy_lib or f"b{str(meta_file.id).zfill(9)}").upper()



def get_work_dir(meta_file: Meta_File) -> str:
  """Directory for generated SQL sources"""

  work_dir = os.path.join(meta_file.meta_dir, 'db_deployment')
  os.makedirs(work_dir, exist_ok=True)
  return work_dir



def split_object_name(name: str) -> tuple[str, str]:
  """LIB/NAME -> (LIB, NAME)"""

  parts = str(name).strip().upper().split('/')
  if len(parts) != 2 or '' in parts:
    raise Db_Deployment_Exception(f"'{name}' is not a qualified object name (LIB/NAME)")
  return check_system_name(parts[0], 'library of a dependent file'), check_system_name(parts[1], 'name of a dependent file')



def check_system_name(name: str, what: str) -> str:

  name = str(name or '').strip().upper()
  if not C_SYSTEM_NAME.fullmatch(name):
    raise Db_Deployment_Exception(f"DB deployment: '{name}' is not a valid system name for the {what}")
  return name



def get_table_configs(meta_file: Meta_File) -> list[dict]:
  """
  Configured tables of a deployment, numbered in their order (no). Names are in upper case.

  Returns:
      list[dict]: no, lib, name, columns, library_list, dependents (list of (lib, name)), settings
  """

  data = (meta_file.custom_data or {}).get('db_deployment') or {}
  tables = []

  for i, table in enumerate(data.get('tables') or [], start=1):

    if not isinstance(table, dict):
      raise Db_Deployment_Exception(f"DB deployment: table {i} needs to be an object with 'lib' and 'name'")

    config = dict(table)
    config['no'] = i
    config['lib'] = check_system_name(table.get('lib'), f"library of table {i}")
    config['name'] = check_system_name(table.get('name'), f"name of table {i}")
    config['columns'] = table.get('columns') or {}
    config['library_list'] = [check_system_name(lib, 'library list') for lib in table.get('library_list') or []]
    config['dependents'] = [split_object_name(d) for d in table.get('dependents') or []]

    if any(t['lib'] == config['lib'] and t['name'] == config['name'] for t in tables):
      raise Db_Deployment_Exception(f"DB deployment: table {config['lib']}/{config['name']} is configured twice")

    tables.append(config)

  return tables



def get_config_hash(table: dict) -> str:
  """Fingerprint of the configuration which defines the content of the new table (not of the settings)"""

  config = {
    'columns': {k.upper(): str(v) for k, v in (table.get('columns') or {}).items()},
    'dependents': sorted(f"{lib}/{name}" for lib, name in table.get('dependents') or []),
    'library_list': table.get('library_list') or [],
  }
  return hashlib.sha256(json.dumps(config, sort_keys=True).encode('utf-8')).hexdigest()



def get_deploy_object(meta_file: Meta_File, lib: str, name: str, attributes: tuple|None=None) -> Deploy_Object|None:
  """Deploy object by its production library and name"""

  for obj in meta_file.deploy_objects:
    if obj.prod_lib == lib.lower() and obj.name == name.lower() and (attributes is None or obj.attribute in attributes):
      return obj

  return None



def get_source_path(meta_file: Meta_File, obj: Deploy_Object) -> str:
  """Source of a deploy object: copied into the meta directory (see obi.load_objects_from_compile_list) or in the build directory"""

  if not obj.source:
    raise Db_Deployment_Exception(f"Deploy object {obj.prod_lib}/{obj.name} has no source")

  candidates = [os.path.join(meta_file.meta_dir, 'src', obj.source)]

  base_dir = (obj.properties or {}).get('remote-base-dir')
  if base_dir:
    candidates.append(os.path.join(os.path.expanduser('~'), base_dir, 'src', obj.source))

  for path in candidates:
    if os.path.isfile(path):
      return os.path.realpath(path)

  raise Db_Deployment_Exception(f"Source of {obj.prod_lib}/{obj.name} not found: {', '.join(candidates)}")



def is_configured_table(meta_file: Meta_File, obj: Deploy_Object) -> bool:

  if obj.attribute not in C_TABLE_ATTRIBUTES:
    return False

  return any(t['lib'] == obj.prod_lib.upper() and t['name'] == obj.name.upper() for t in get_table_configs(meta_file))



def is_db_deployment_object(meta_file: Meta_File, obj: Deploy_Object) -> bool:
  """The object is deployed by the DB deployment, so it must not be saved or deployed by other steps"""
  return bool((obj.properties or {}).get(C_PROPERTY)) or is_configured_table(meta_file, obj)



def check_deploy_object(meta_file: Meta_File, obj: Deploy_Object) -> bool:
  """
  For deployment steps (e.g. obi.perform_deployment): an object which belongs to the DB deployment must not be deployed again.

  Returns:
      bool: True if the object has been deployed by the DB deployment, so it has to be skipped

  Raises:
      Db_Deployment_Exception: The object belongs to the DB deployment, but the cut-over has not been done yet
  """

  status = (obj.properties or {}).get(C_PROPERTY)

  if status == C_DEPLOYED:
    return True

  if status or is_configured_table(meta_file, obj):
    raise Db_Deployment_Exception(f"{obj.prod_lib}/{obj.name} is deployed by the DB deployment. Run step db-cutover first.")

  return False



def set_status(objects: list[Deploy_Object], status: str) -> None:

  for obj in objects:
    if obj.properties is None:
      obj.properties = {}
    obj.properties[C_PROPERTY] = status
    if status == C_DEPLOYED:
      obj.deploy_status = Obj_Status.FINISHED
