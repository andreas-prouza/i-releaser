"""
Information about tables and other objects from the system catalog of Db2 for i

All names are system names in upper case.
Commands which write an outfile (DSPDBR, DSPFD) use QTEMP of the connection.
"""
from __future__ import annotations

import logging

from modules.db_deployment.connection import Connection, get_error_text



def get_table(db: Connection, lib: str, name: str) -> dict|None:
  """
  Returns:
      dict: table_schema, table_name (SQL names), system_table_schema, system_table_name,
            table_type (T: SQL table, P: physical file, L: logical file, V: view, ...), file_type (D: data, S: source)
  """

  rows = db.query("SELECT TABLE_SCHEMA, TABLE_NAME, SYSTEM_TABLE_SCHEMA, SYSTEM_TABLE_NAME, TABLE_TYPE, FILE_TYPE "
                  "FROM QSYS2.SYSTABLES WHERE SYSTEM_TABLE_SCHEMA = ? AND SYSTEM_TABLE_NAME = ?", [lib, name])
  return rows[0] if len(rows) > 0 else None



def find_table_by_sql_name(db: Connection, lib: str, sql_name: str) -> dict|None:

  rows = db.query("SELECT TABLE_SCHEMA, TABLE_NAME, SYSTEM_TABLE_SCHEMA, SYSTEM_TABLE_NAME, TABLE_TYPE, FILE_TYPE "
                  "FROM QSYS2.SYSTABLES WHERE SYSTEM_TABLE_SCHEMA = ? AND TABLE_NAME = ?", [lib, sql_name])
  return rows[0] if len(rows) > 0 else None



def get_columns(db: Connection, lib: str, name: str) -> list[dict]:
  """
  Columns in their order

  Returns:
      list[dict]: column_name, system_column_name, data_type, is_nullable (Y/N), has_default, is_identity (YES/NO),
                  identity_generation (ALWAYS/BY DEFAULT)
  """

  return db.query("SELECT COLUMN_NAME, SYSTEM_COLUMN_NAME, DATA_TYPE, IS_NULLABLE, HAS_DEFAULT, IS_IDENTITY, IDENTITY_GENERATION "
                  "FROM QSYS2.SYSCOLUMNS WHERE SYSTEM_TABLE_SCHEMA = ? AND SYSTEM_TABLE_NAME = ? ORDER BY ORDINAL_POSITION", [lib, name])



def get_member_count(db: Connection, lib: str, name: str) -> int:
  return db.query_value("SELECT COUNT(*) FROM QSYS2.SYSPARTITIONSTAT WHERE SYSTEM_TABLE_SCHEMA = ? AND SYSTEM_TABLE_NAME = ?", [lib, name]) or 0



def get_size(db: Connection, lib: str, name: str) -> int:
  """
  Number of records including the deleted ones of the (only) member.
  As long as deleted records are not reused, the next inserted row gets the relative record number size + 1.
  """

  rows = db.query("SELECT NUMBER_ROWS, NUMBER_DELETED_ROWS FROM QSYS2.SYSPARTITIONSTAT "
                  "WHERE SYSTEM_TABLE_SCHEMA = ? AND SYSTEM_TABLE_NAME = ?", [lib, name])
  if len(rows) != 1:
    raise Exception(f"{lib}/{name} has {len(rows)} members, expected 1")

  return int(rows[0]['number_rows'] or 0) + int(rows[0]['number_deleted_rows'] or 0)



def get_row_count(db: Connection, table: str) -> int:
  """COUNT(*) without a condition is taken from the member, so it doesn't read the table"""
  return int(db.query_value(f"SELECT COUNT(*) FROM {table}") or 0)



def get_triggers(db: Connection, table: dict) -> list[str]:
  """Triggers of a table (SQL and system triggers)"""

  rows = db.query("SELECT TRIGGER_SCHEMA, TRIGGER_NAME FROM QSYS2.SYSTRIGGERS WHERE EVENT_OBJECT_SCHEMA = ? AND EVENT_OBJECT_TABLE = ?",
                  [table['table_schema'], table['table_name']])
  return [f"{r['trigger_schema']}.{r['trigger_name']}" for r in rows]



def get_foreign_keys(db: Connection, lib: str, name: str) -> list[str]:
  """Foreign keys of the table and foreign keys of other tables which reference it"""

  rows = db.query("SELECT CONSTRAINT_SCHEMA, CONSTRAINT_NAME FROM QSYS2.SYSCST "
                  "WHERE SYSTEM_TABLE_SCHEMA = ? AND SYSTEM_TABLE_NAME = ? AND CONSTRAINT_TYPE = 'FOREIGN KEY'", [lib, name])

  rows += db.query("SELECT R.CONSTRAINT_SCHEMA, R.CONSTRAINT_NAME FROM QSYS2.SYSREFCST R "
                   "JOIN QSYS2.SYSCST C ON C.CONSTRAINT_SCHEMA = R.UNIQUE_CONSTRAINT_SCHEMA AND C.CONSTRAINT_NAME = R.UNIQUE_CONSTRAINT_NAME "
                   "WHERE C.SYSTEM_TABLE_SCHEMA = ? AND C.SYSTEM_TABLE_NAME = ?", [lib, name])

  return [f"{r['constraint_schema']}.{r['constraint_name']}" for r in rows]



def get_dependents(db: Connection, lib: str, name: str) -> list[dict]:
  """
  Files which depend on a physical file or table: logical files, SQL indexes and views (DSPDBR)

  Returns:
      list[dict]: lib, name, kind (index, lf, view, other)
  """

  db.qcmdexc(f"DSPDBR FILE({lib}/{name}) OUTPUT(*OUTFILE) OUTFILE(QTEMP/IRDBR) OUTMBR(*FIRST *REPLACE)")
  rows = db.query("SELECT DISTINCT WHRELI, WHREFI FROM QTEMP.IRDBR WHERE WHREFI <> '' ORDER BY WHRELI, WHREFI")

  dependents = []
  for r in rows:
    dep_lib, dep_name = r['whreli'].strip(), r['whrefi'].strip()
    dependents.append({'lib': dep_lib, 'name': dep_name, 'kind': get_file_kind(db, dep_lib, dep_name)})

  return dependents



def get_file_kind(db: Connection, lib: str, name: str) -> str:
  """index (SQL index), lf (DDS logical file), view (SQL view), table, other"""

  if db.query_value("SELECT COUNT(*) FROM QSYS2.SYSINDEXES WHERE SYSTEM_INDEX_SCHEMA = ? AND SYSTEM_INDEX_NAME = ?", [lib, name]):
    return 'index'

  table = get_table(db, lib, name)
  if table is None:
    return 'other'

  return {'L': 'lf', 'V': 'view', 'T': 'table', 'P': 'table'}.get(table['table_type'], 'other')



def get_object_info(db: Connection, lib: str, name: str, obj_type: str='*FILE') -> dict|None:
  """
  Returns:
      dict: objowner, journaled (YES/NO), journal_library, journal_name, journal_images (*AFTER/*BOTH),
            omit_journal_entry (*NONE/*OPNCLO), source_file, source_library, source_member
  """

  rows = db.query("SELECT OBJOWNER, JOURNALED, JOURNAL_LIBRARY, JOURNAL_NAME, JOURNAL_IMAGES, OMIT_JOURNAL_ENTRY, "
                  "SOURCE_FILE, SOURCE_LIBRARY, SOURCE_MEMBER FROM TABLE(QSYS2.OBJECT_STATISTICS(?, ?, ?)) X",
                  [lib, obj_type, name])
  if len(rows) == 0:
    return None

  return {k: v.strip() if isinstance(v, str) else v for k, v in rows[0].items()}



def object_exists(db: Connection, lib: str, name: str, obj_type: str='*FILE') -> bool:

  try:
    return (db.query_value("SELECT COUNT(*) FROM TABLE(QSYS2.OBJECT_STATISTICS(?, ?, ?)) X", [lib, obj_type, name]) or 0) > 0
  except Exception as e:
    # E.g. the library doesn't exist
    logging.debug(f"Check of {lib}/{name} ({obj_type}) failed: {get_error_text(e)}")
    return False



def library_exists(db: Connection, lib: str) -> bool:
  return object_exists(db, 'QSYS', lib, '*LIB')



def get_reuse_deleted(db: Connection, lib: str, name: str) -> bool|None:
  """REUSEDLT attribute of a physical file (DSPFD), None if it can't be retrieved"""

  try:
    db.qcmdexc(f"DSPFD FILE({lib}/{name}) TYPE(*ATR) OUTPUT(*OUTFILE) FILEATR(*PF) OUTFILE(QTEMP/IRFDPHY) OUTMBR(*FIRST *REPLACE)")
    value = db.query_value("SELECT PHRUSE FROM QTEMP.IRFDPHY")
  except Exception as e:
    logging.warning(f"REUSEDLT of {lib}/{name} can't be retrieved: {get_error_text(e)}")
    return None

  if value is None:
    return None
  return value.strip() == 'Y'



def get_journal_delete_receiver_option(db: Connection, jrn_lib: str, jrn: str) -> str|None:
  """'YES' if the system deletes detached receivers"""

  try:
    return db.query_value("SELECT DELETE_RECEIVER_OPTION FROM QSYS2.JOURNAL_INFO WHERE JOURNAL_LIBRARY = ? AND JOURNAL_NAME = ?", [jrn_lib, jrn])
  except Exception as e:
    logging.debug(f"Journal info of {jrn_lib}/{jrn} not available: {get_error_text(e)}")
    return None



def get_lock_holders(db: Connection, objects: list[tuple[str, str]]) -> list[str]:
  """Jobs which hold a lock on one of the files, for error messages"""

  holders = []

  for lib, name in objects:
    try:
      rows = db.query("SELECT JOB_NAME, LOCK_STATE FROM QSYS2.OBJECT_LOCK_INFO "
                      "WHERE SYSTEM_OBJECT_SCHEMA = ? AND SYSTEM_OBJECT_NAME = ? AND OBJECT_TYPE = '*FILE'", [lib, name])
    except Exception as e:
      logging.debug(f"Lock info of {lib}/{name} not available: {get_error_text(e)}")
      continue

    for r in rows:
      holder = f"{r['job_name']} ({lib}/{name} {r['lock_state']})"
      if holder not in holders:
        holders.append(holder)

  return holders



def get_current_timestamp(db: Connection):
  return db.query_value("SELECT CURRENT TIMESTAMP FROM SYSIBM.SYSDUMMY1")
