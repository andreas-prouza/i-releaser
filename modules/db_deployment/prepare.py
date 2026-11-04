"""
Step db-prepare: builds the new table and its dependent files in the shadow library

* New table, and logical files / indexes of the deployment: from their source in the deployment
* Other SQL indexes over the old table: from SQL generated for them (QSYS2.GENERATE_SQL)
* Other logical files over the old table: from the source member they have been created from
* Views over the old table: SQL is generated now, they are created again after the cut-over

Then the old table is journaled (if not yet), the work tables are created and the column mapping is tested.
Running it again for a prepared table does nothing. A failed table is prepared again from scratch.
"""
from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING

from modules.db_deployment import catalog, objects, state, sync
from modules.db_deployment.connection import Connection, Db_Deployment_Exception, sql_table
from modules.db_deployment.state import Table_State, Phase, Replaced_Object

if TYPE_CHECKING:
  from modules.meta_file import Meta_File
  from modules.deploy_object import Deploy_Object


# These statements would make unqualified names point to another library than the shadow library
C_FORBIDDEN_STATEMENTS = re.compile(r'^\s*SET\s+(CURRENT\s+)?SCHEMA\b', re.IGNORECASE | re.MULTILINE)



def prepare_table(db: Connection, meta_file: Meta_File, table: dict, settings: dict) -> list[Deploy_Object]:
  """
  Returns:
      list[Deploy_Object]: Deploy objects which are built in the shadow library
  """

  shadow_lib = objects.get_shadow_lib(meta_file)
  lib, name, no = table['lib'], table['name'], table['no']

  ensure_shadow_lib(db, meta_file, shadow_lib)
  state.create_state_tables(db, shadow_lib)

  st = Table_State(db, shadow_lib, no, lib, name).load()

  config_hash = objects.get_config_hash(table)
  changed = st.config_hash != config_hash

  if st.exists and st.phase in (Phase.CUTOVER, Phase.SWAPPED, Phase.DONE):
    if changed:
      logging.warning(f"The configuration of {lib}/{name} has changed, but its cut-over has started already (phase {st.phase.value})")
    return get_deploy_objects(meta_file, state.load_objects(db, shadow_lib, no))

  if st.exists and st.phase not in (Phase.NEW, Phase.FAILED):
    if not changed:
      logging.info(f"{lib}/{name} is already prepared (phase {st.phase.value})")
      return get_deploy_objects(meta_file, state.load_objects(db, shadow_lib, no))
    st.message = 'configuration changed'

  if st.exists:
    logging.info(f"Prepare {lib}/{name} again (phase {st.phase.value}{': ' + st.message if st.message else ''})")
    remove_shadow_objects(db, shadow_lib, st)

  prod_table = check_table(db, meta_file, lib, name)
  replaced = get_replaced_objects(db, meta_file, table)
  logging.info(f"Objects which are replaced at the cut-over: {replaced}")

  st.phase = Phase.NEW
  st.message = ''
  st.config_hash = config_hash
  st.save()
  state.save_objects(db, shadow_lib, no, replaced)

  build_shadow_objects(db, meta_file, table, prod_table, replaced, st)
  start_journaling(db, st)

  state.create_work_tables(db, shadow_lib, no)

  table_sync = sync.open_table_sync(db, shadow_lib, table, settings)
  for warning in table_sync.mapping.warnings:
    logging.warning(f"{lib}/{name}: {warning}")
  logging.info(f"{lib}/{name}: columns {', '.join(f'{c} = {e}' for c, e in zip(table_sync.mapping.columns, table_sync.mapping.expressions))}")

  table_sync.open()
  table_sync.test()

  # Changes from now on are applied from the journal
  st.start_time = catalog.get_current_timestamp(db)
  st.receiver_lib = ''
  st.receiver_name = ''
  st.journal_sequence = 0
  st.copy_next_rrn = 1
  st.copy_end_rrn = 0
  st.target_size = table_sync.get_size()
  st.rows_copied = 0
  st.rows_applied = 0
  st.set_phase(Phase.PREPARED, '')

  logging.info(f"{lib}/{name} is prepared in {shadow_lib}, changes are taken from journal {st.journal_lib}/{st.journal_name} since {st.start_time}")

  return get_deploy_objects(meta_file, replaced)



def get_deploy_objects(meta_file: Meta_File, replaced: list[Replaced_Object]) -> list[Deploy_Object]:
  """Deploy objects of the replaced objects which are built from the source of the deployment"""

  result = []
  for o in replaced:
    if o.origin == 'deployment':
      obj = objects.get_deploy_object(meta_file, o.prod_lib, o.name)
      if obj is not None:
        result.append(obj)
  return result



def ensure_shadow_lib(db: Connection, meta_file: Meta_File, shadow_lib: str) -> None:
  """CRTLIB, not CREATE SCHEMA: the tables of the shadow library must not be journaled"""

  if catalog.library_exists(db, shadow_lib):
    return

  db.qcmdexc(f"CRTLIB LIB({shadow_lib}) TEXT('i-Releaser: new tables of deployment {meta_file.id}')")



def check_table(db: Connection, meta_file: Meta_File, lib: str, name: str) -> dict:
  """Checks whether the old table can be deployed this way"""

  prod_table = catalog.get_table(db, lib, name)

  if prod_table is None:
    raise Db_Deployment_Exception(f"{lib}/{name} doesn't exist")

  if prod_table['table_type'] not in ('T', 'P') or (prod_table['file_type'] or 'D') != 'D':
    raise Db_Deployment_Exception(f"{lib}/{name} is not a table or physical data file (type {prod_table['table_type']})")

  members = catalog.get_member_count(db, lib, name)
  if members != 1:
    raise Db_Deployment_Exception(f"{lib}/{name} has {members} members. Only files with one member are supported.")

  unsupported = catalog.get_triggers(db, prod_table) + catalog.get_foreign_keys(db, lib, name)
  if len(unsupported) > 0:
    raise Db_Deployment_Exception(f"{lib}/{name} has triggers or foreign keys, which are not supported yet: {', '.join(unsupported)}. "
                                  "Remove them before and add them after the deployment with your own steps.")

  if objects.get_deploy_object(meta_file, lib, name, objects.C_TABLE_ATTRIBUTES) is None:
    raise Db_Deployment_Exception(f"{lib}/{name} is not part of the deployment (no deploy object with attribute {' or '.join(objects.C_TABLE_ATTRIBUTES)})")

  return prod_table



def get_replaced_objects(db: Connection, meta_file: Meta_File, table: dict) -> list[Replaced_Object]:
  """The table and the files which depend on it"""

  lib, name, no = table['lib'], table['name'], table['no']
  replaced = [Replaced_Object(no, 0, 'table', 'deployment', lib, name, in_prod=True)]

  for dep in catalog.get_dependents(db, lib, name):

    obj = objects.get_deploy_object(meta_file, dep['lib'], dep['name'])

    if dep['kind'] == 'view':
      if obj is not None:
        logging.info(f"View {dep['lib']}/{dep['name']} is part of the deployment, it's created by the deployment after the cut-over")
        continue
      origin = 'view'

    elif dep['kind'] in ('index', 'lf'):
      if obj is not None:
        if obj.attribute not in objects.C_DEPENDENT_ATTRIBUTES:
          raise Db_Deployment_Exception(f"{dep['lib']}/{dep['name']} depends on {lib}/{name}, "
                                        f"its deploy object has attribute {obj.attribute} instead of {' or '.join(objects.C_DEPENDENT_ATTRIBUTES)}")
        origin = 'deployment'
      else:
        origin = 'generated' if dep['kind'] == 'index' else 'source'

    else:
      raise Db_Deployment_Exception(f"{dep['lib']}/{dep['name']} ({dep['kind']}) depends on {lib}/{name}, this kind of dependency is not supported")

    replaced.append(Replaced_Object(no, len(replaced), dep['kind'], origin, dep['lib'], dep['name'], in_prod=True))

  # New logical files and indexes of the deployment, which are built over the new table
  for dep_lib, dep_name in table.get('dependents') or []:

    if any(o.prod_lib == dep_lib and o.name == dep_name for o in replaced):
      continue

    obj = objects.get_deploy_object(meta_file, dep_lib, dep_name, objects.C_DEPENDENT_ATTRIBUTES)
    if obj is None:
      raise Db_Deployment_Exception(f"Dependent {dep_lib}/{dep_name} of {lib}/{name} is not part of the deployment "
                                    f"(no deploy object with attribute {' or '.join(objects.C_DEPENDENT_ATTRIBUTES)})")

    if catalog.object_exists(db, dep_lib, dep_name):
      raise Db_Deployment_Exception(f"Dependent {dep_lib}/{dep_name} exists, but it doesn't depend on {lib}/{name}")

    kind = 'lf' if obj.attribute == 'lf' else 'index'
    replaced.append(Replaced_Object(no, len(replaced), kind, 'deployment', dep_lib, dep_name, in_prod=False))

  names = [o.name for o in replaced if o.is_moved()]
  duplicates = sorted({n for n in names if names.count(n) > 1})
  if len(duplicates) > 0:
    raise Db_Deployment_Exception(f"Files with the same name can't be built in the shadow library: {', '.join(duplicates)}")

  return replaced



def remove_shadow_objects(db: Connection, shadow_lib: str, st: Table_State) -> None:
  """Removes what a former prepare of the table has built"""

  for o in reversed(state.load_objects(db, shadow_lib, st.no)):
    if o.is_moved() and catalog.object_exists(db, shadow_lib, o.name):
      db.qcmdexc(f"DLTF FILE({shadow_lib}/{o.name})")

  state.drop_work_tables(db, shadow_lib, st.no)



def build_shadow_objects(db: Connection, meta_file: Meta_File, table: dict, prod_table: dict, replaced: list[Replaced_Object],
                         st: Table_State) -> None:

  shadow_lib = st.shadow_lib
  lib, name = st.prod_lib, st.prod_file

  # Unqualified files (e.g. PFILE of a logical file) are found in the shadow library first
  db.qcmdexc(f"ADDLIBLE LIB({shadow_lib}) POSITION(*FIRST)", ignore_errors=True)
  for library in table.get('library_list') or []:
    db.qcmdexc(f"ADDLIBLE LIB({library}) POSITION(*LAST)", ignore_errors=True)

  try:
    table_obj = objects.get_deploy_object(meta_file, lib, name, objects.C_TABLE_ATTRIBUTES)
    table_libs = [table_obj.lib, table_obj.prod_lib]
    build_from_source(db, meta_file, table_obj, shadow_lib, table_libs, [name, prod_table['table_name']])
    check_shadow_table(db, shadow_lib, prod_table)

    st.reuse_deleted = catalog.get_reuse_deleted(db, shadow_lib, name)
    if st.reuse_deleted is None:
      st.reuse_deleted = prod_table['table_type'] == 'T'
    db.qcmdexc(f"CHGPF FILE({shadow_lib}/{name}) REUSEDLT(*NO) SIZE(*NOMAX)")

    for o in replaced[1:]:

      if o.origin == 'deployment':
        obj = objects.get_deploy_object(meta_file, o.prod_lib, o.name)
        build_from_source(db, meta_file, obj, shadow_lib, table_libs + [obj.lib, obj.prod_lib], [name, prod_table['table_name'], o.name])
      elif o.origin == 'generated':
        build_generated_index(db, meta_file, o, shadow_lib)
      elif o.origin == 'source':
        build_lf_from_member(db, o, shadow_lib)
      elif o.origin == 'view':
        generate_view_sql(db, meta_file, o)

    check_shadow_dependents(db, shadow_lib, name, replaced)

  finally:
    db.qcmdexc(f"RMVLIBLE LIB({shadow_lib})", ignore_errors=True)



def build_from_source(db: Connection, meta_file: Meta_File, obj: Deploy_Object, shadow_lib: str, libs: list[str], names: list[str]) -> None:
  """
  Builds a deploy object from its source in the shadow library, like obi.py does in production

  Args:
      libs: libraries which are replaced by the shadow library in SQL sources, if they qualify one of the names
  """

  source = objects.get_source_path(meta_file, obj)
  logging.info(f"Build {obj.prod_lib}/{obj.name} ({obj.attribute}) in {shadow_lib} from {source}")

  if obj.attribute in ('sqltable', 'sqlindex'):

    with open(source, 'r', encoding='utf-8', errors='replace') as f:
      text = f.read()

    text = get_shadow_sql(text, libs, names, shadow_lib)
    run_sql_source(db, meta_file, text, f"{obj.name.upper()}.{obj.attribute}.sql", shadow_lib)
    return

  if obj.attribute in ('pf', 'lf'):

    member = obj.name.upper()
    db.qcmdexc("DLTF FILE(QTEMP/IRSRC)", ignore_errors=True)
    db.qcmdexc("CRTSRCPF FILE(QTEMP/IRSRC) RCDLEN(112)")
    db.qcmdexc(f"CPYFRMSTMF FROMSTMF('{source}') TOMBR('/QSYS.LIB/QTEMP.LIB/IRSRC.FILE/{member}.MBR') MBROPT(*REPLACE)")
    db.qcmdexc(f"{'CRTPF' if obj.attribute == 'pf' else 'CRTLF'} FILE({shadow_lib}/{member}) SRCFILE(QTEMP/IRSRC) SRCMBR({member})")
    return

  raise Db_Deployment_Exception(f"{obj.prod_lib}/{obj.name}: attribute {obj.attribute} can't be built in the shadow library")



def get_shadow_sql(text: str, libs: list[str], names: list[str], shadow_lib: str) -> str:
  """
  Qualifies the given objects with the shadow library instead of their libraries (LIB.NAME, "LIB"."NAME", LIB/NAME).
  Unqualified names are put into the shadow library by RUNSQLSTM (DFTRDBCOL).
  """

  if C_FORBIDDEN_STATEMENTS.search(text):
    raise Db_Deployment_Exception("SQL source contains SET SCHEMA. Use qualified or unqualified names instead, "
                                  "so the objects can be built in the shadow library.")

  libs = sorted({l.upper() for l in libs if l}, key=len, reverse=True)
  names = sorted({n.upper() for n in names if n}, key=len, reverse=True)

  pattern = re.compile(rf'(?<![\w$#@"])"?(?:{"|".join(re.escape(l) for l in libs)})"?\s*[./]\s*'
                       rf'(?="?(?:{"|".join(re.escape(n) for n in names)})"?(?![\w$#@]))',
                       re.IGNORECASE)

  return pattern.sub(f'{shadow_lib}.', text)



def run_sql_source(db: Connection, meta_file: Meta_File, text: str, file_name: str, shadow_lib: str) -> None:
  """
  Runs SQL statements with SQL naming and the shadow library as default schema,
  so unqualified names never point to a production library (as the library list would do with system naming).
  """

  path = os.path.join(objects.get_work_dir(meta_file), file_name)
  with open(path, 'w', encoding='utf-8') as f:
    f.write(text)

  db.qcmdexc(f"CHGATR OBJ('{path}') ATR(*CCSID) VALUE(1208)")
  db.qcmdexc(f"RUNSQLSTM SRCSTMF('{path}') COMMIT(*NONE) NAMING(*SQL) DFTRDBCOL({shadow_lib}) ERRLVL(21)")



def get_generated_sql(db: Connection, lib: str, name: str, object_type: str, qualified: bool) -> str:
  """SQL of an existing object (QSYS2.GENERATE_SQL into QTEMP/Q_GENSQL)"""

  db.execute("CALL QSYS2.GENERATE_SQL(DATABASE_OBJECT_NAME => ?, DATABASE_OBJECT_LIBRARY_NAME => ?, DATABASE_OBJECT_TYPE => ?, "
             "DATABASE_SOURCE_FILE_NAME => 'Q_GENSQL', DATABASE_SOURCE_FILE_LIBRARY_NAME => 'QTEMP', DATABASE_SOURCE_FILE_MEMBER => 'Q_GENSQL', "
             "REPLACE_OPTION => '1', QUALIFIED_NAME_OPTION => ?, CREATE_OR_REPLACE_OPTION => ?)",
             [name, lib, object_type, '0' if qualified else '1', '1' if qualified else '0'])

  rows = db.query("SELECT SRCDTA FROM QTEMP.Q_GENSQL ORDER BY SRCSEQ")
  return '\n'.join((r['srcdta'] or '').rstrip() for r in rows)



def build_generated_index(db: Connection, meta_file: Meta_File, o: Replaced_Object, shadow_lib: str) -> None:
  """SQL index which isn't part of the deployment: its SQL with unqualified names is run in the shadow library"""

  logging.info(f"Build index {o.prod_lib}/{o.name} in {shadow_lib} from its generated SQL")

  text = get_generated_sql(db, o.prod_lib, o.name, 'INDEX', qualified=False)
  # GENERATE_SQL may set the schema of the object, the shadow library is set by RUNSQLSTM
  text = C_FORBIDDEN_STATEMENTS.sub('-- ', text)
  run_sql_source(db, meta_file, text, f"{o.name}.index.sql", shadow_lib)



def build_lf_from_member(db: Connection, o: Replaced_Object, shadow_lib: str) -> None:
  """Logical file which isn't part of the deployment: built from the source member it has been created from"""

  info = catalog.get_object_info(db, o.prod_lib, o.name) or {}
  src_lib, src_file, src_member = info.get('source_library'), info.get('source_file'), info.get('source_member')

  if not src_lib or not src_file or not src_member or not catalog.object_exists(db, src_lib, src_file):
    raise Db_Deployment_Exception(f"Logical file {o.prod_lib}/{o.name} depends on the table, but its source is not available "
                                  f"({src_lib}/{src_file}({src_member})). Add it to the deployment.")

  logging.info(f"Build logical file {o.prod_lib}/{o.name} in {shadow_lib} from {src_lib}/{src_file}({src_member})")
  db.qcmdexc(f"CRTLF FILE({shadow_lib}/{o.name}) SRCFILE({src_lib}/{src_file}) SRCMBR({src_member})")



def get_view_source(meta_file: Meta_File, o: Replaced_Object) -> str:
  return os.path.join(objects.get_work_dir(meta_file), f"{o.prod_lib}.{o.name}.view.sql")



def generate_view_sql(db: Connection, meta_file: Meta_File, o: Replaced_Object) -> None:
  """A view keeps pointing to the old table, so it's created again (CREATE OR REPLACE) after the cut-over"""

  text = get_generated_sql(db, o.prod_lib, o.name, 'VIEW', qualified=True)
  with open(get_view_source(meta_file, o), 'w', encoding='utf-8') as f:
    f.write(text)
  logging.info(f"SQL of view {o.prod_lib}/{o.name} saved, it's created again after the cut-over")



def check_shadow_table(db: Connection, shadow_lib: str, prod_table: dict) -> None:
  """The new table must have the same system name as the old one and must not have triggers or foreign keys"""

  name = prod_table['system_table_name']
  shadow_table = catalog.get_table(db, shadow_lib, name)

  if shadow_table is None and prod_table['table_name'] != name:
    # SQL table with a long name, created without FOR SYSTEM NAME
    shadow_table = catalog.find_table_by_sql_name(db, shadow_lib, prod_table['table_name'])
    if shadow_table is not None:
      logging.info(f"Rename system name of {shadow_lib}/{shadow_table['system_table_name']} to {name}")
      db.execute(f"RENAME TABLE {sql_table(shadow_lib, shadow_table['system_table_name'])} TO SYSTEM NAME {name}")
      shadow_table = catalog.get_table(db, shadow_lib, name)

  if shadow_table is None:
    raise Db_Deployment_Exception(f"The source of {prod_table['system_table_schema']}/{name} hasn't built {shadow_lib}/{name}")

  unsupported = catalog.get_triggers(db, shadow_table) + catalog.get_foreign_keys(db, shadow_lib, name)
  if len(unsupported) > 0:
    raise Db_Deployment_Exception(f"The new table has triggers or foreign keys, which are not supported yet: {', '.join(unsupported)}")

  info = catalog.get_object_info(db, shadow_lib, name) or {}
  if info.get('journaled') == 'YES':
    logging.warning(f"{shadow_lib}/{name} is journaled ({info.get('journal_library')}/{info.get('journal_name')}), that slows down the copy")



def check_shadow_dependents(db: Connection, shadow_lib: str, name: str, replaced: list[Replaced_Object]) -> None:
  """Each dependent file has to be built over the new table"""

  built = {(d['lib'], d['name']) for d in catalog.get_dependents(db, shadow_lib, name)}

  for o in replaced[1:]:
    if o.is_moved() and (shadow_lib, o.name) not in built:
      raise Db_Deployment_Exception(f"{o.prod_lib}/{o.name} has not been built over {shadow_lib}/{name}. "
                                    "Check its source: the table has to be referenced unqualified or with its production library.")



def start_journaling(db: Connection, st: Table_State) -> None:
  """The changes of the old table are taken from its journal. If it isn't journaled, a journal is created in the shadow library."""

  shadow_lib = st.shadow_lib
  info = catalog.get_object_info(db, st.prod_lib, st.prod_file) or {}

  if info.get('journaled') == 'YES':
    st.journal_lib = info['journal_library']
    st.journal_name = info['journal_name']
    st.journal_started = st.journal_lib == shadow_lib and st.journal_name == state.C_JOURNAL

    if catalog.get_journal_delete_receiver_option(db, st.journal_lib, st.journal_name) == 'YES':
      logging.warning(f"Journal {st.journal_lib}/{st.journal_name} deletes detached receivers. "
                      "They are needed until the cut-over, otherwise the table has to be prepared and copied again.")
    return

  if not catalog.object_exists(db, shadow_lib, state.C_JOURNAL, '*JRN'):
    db.qcmdexc(f"CRTJRNRCV JRNRCV({shadow_lib}/{state.C_JOURNAL_RECEIVER}) TEXT('i-Releaser DB deployment')")
    db.qcmdexc(f"CRTJRN JRN({shadow_lib}/{state.C_JOURNAL}) JRNRCV({shadow_lib}/{state.C_JOURNAL_RECEIVER}) "
               "MNGRCV(*SYSTEM) DLTRCV(*NO) RCVSIZOPT(*MAXOPT3) TEXT('i-Releaser DB deployment')")

  # Only the relative record numbers are needed, so after images are enough
  db.qcmdexc(f"STRJRNPF FILE({st.prod_lib}/{st.prod_file}) JRN({shadow_lib}/{state.C_JOURNAL}) IMAGES(*AFTER) OMTJRNE(*OPNCLO)")

  st.journal_lib = shadow_lib
  st.journal_name = state.C_JOURNAL
  st.journal_started = True
