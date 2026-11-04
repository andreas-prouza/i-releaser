"""
Runtime state of a DB deployment, stored in the shadow library on the target system

* IRSTATE    One row per table: phase, journal position, progress of the copy
* IROBJECTS  Objects which are replaced at the cut-over: the table and its dependent files
* IRMAPnnn   Relative record number of each row in the old table (SRC_RRN) and in the new table (TGT_RRN)
* IRCHGnnn   Rows of the old table which have changed and wait to be applied
* IRERRnnn   Rows which could not be applied (e.g. duplicate key, conversion error), with the error

Like this the state doesn't depend on the deployment data of i-Releaser,
and a step can be run again: it continues where it has stopped.
"""
from __future__ import annotations

from enum import Enum

from modules.db_deployment.connection import Connection, Db_Deployment_Exception, sql_table
from modules.db_deployment.objects import get_config_hash


C_STATE_TABLE = 'IRSTATE'
C_OBJECTS_TABLE = 'IROBJECTS'
C_JOURNAL = 'IRJRN'
C_JOURNAL_RECEIVER = 'IRRCV0001'



class Phase(Enum):
  NEW = 'NEW'
  PREPARED = 'PREPARED'
  COPYING = 'COPYING'
  COPIED = 'COPIED'
  CUTOVER = 'CUTOVER'
  SWAPPED = 'SWAPPED'
  DONE = 'DONE'
  FAILED = 'FAILED'



def get_map_table(no: int) -> str:
  return f"IRMAP{no:03}"

def get_changes_table(no: int) -> str:
  return f"IRCHG{no:03}"

def get_errors_table(no: int) -> str:
  return f"IRERR{no:03}"

def get_stage_table(no: int) -> str:
  """Table in QTEMP for the rows of the old table which are processed, converted to the new table"""
  return f"IRNEW{no:03}"



def create_state_tables(db: Connection, shadow_lib: str) -> None:

  if not table_exists(db, shadow_lib, C_STATE_TABLE):
    db.execute(f"""CREATE TABLE {sql_table(shadow_lib, C_STATE_TABLE)} (
                     TABLE_NO INTEGER NOT NULL PRIMARY KEY,
                     PROD_LIB VARCHAR(10) NOT NULL,
                     PROD_FILE VARCHAR(10) NOT NULL,
                     PHASE VARCHAR(10) NOT NULL,
                     JOURNAL_LIB VARCHAR(10) NOT NULL DEFAULT '',
                     JOURNAL_NAME VARCHAR(10) NOT NULL DEFAULT '',
                     JOURNAL_STARTED CHAR(1) NOT NULL DEFAULT 'N',
                     RECEIVER_LIB VARCHAR(10) NOT NULL DEFAULT '',
                     RECEIVER_NAME VARCHAR(10) NOT NULL DEFAULT '',
                     JOURNAL_SEQUENCE DECIMAL(21, 0) NOT NULL DEFAULT 0,
                     START_TIME TIMESTAMP,
                     COPY_NEXT_RRN BIGINT NOT NULL DEFAULT 1,
                     COPY_END_RRN BIGINT NOT NULL DEFAULT 0,
                     TARGET_SIZE BIGINT NOT NULL DEFAULT 0,
                     REUSE_DELETED CHAR(1) NOT NULL DEFAULT 'N',
                     ROWS_COPIED BIGINT NOT NULL DEFAULT 0,
                     ROWS_APPLIED BIGINT NOT NULL DEFAULT 0,
                     CONFIG_HASH VARCHAR(64) NOT NULL DEFAULT '',
                     MESSAGE VARCHAR(2000) NOT NULL DEFAULT '',
                     UPDATE_TIME TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP)""")

  if not table_exists(db, shadow_lib, C_OBJECTS_TABLE):
    db.execute(f"""CREATE TABLE {sql_table(shadow_lib, C_OBJECTS_TABLE)} (
                     TABLE_NO INTEGER NOT NULL,
                     SEQ INTEGER NOT NULL,
                     KIND VARCHAR(10) NOT NULL,
                     ORIGIN VARCHAR(10) NOT NULL,
                     PROD_LIB VARCHAR(10) NOT NULL,
                     NAME VARCHAR(10) NOT NULL,
                     IN_PROD CHAR(1) NOT NULL,
                     OLD_MOVED CHAR(1) NOT NULL DEFAULT 'N',
                     NEW_MOVED CHAR(1) NOT NULL DEFAULT 'N',
                     PRIMARY KEY (TABLE_NO, SEQ))""")



def create_work_tables(db: Connection, shadow_lib: str, no: int) -> None:

  drop_work_tables(db, shadow_lib, no)

  map_table = sql_table(shadow_lib, get_map_table(no))
  db.execute(f"CREATE TABLE {map_table} (SRC_RRN BIGINT NOT NULL PRIMARY KEY, TGT_RRN BIGINT NOT NULL)")
  db.execute(f"CREATE UNIQUE INDEX {sql_table(shadow_lib, get_map_table(no) + 'T')} ON {map_table} (TGT_RRN)")
  db.execute(f"CREATE TABLE {sql_table(shadow_lib, get_changes_table(no))} (SRC_RRN BIGINT NOT NULL PRIMARY KEY)")
  db.execute(f"CREATE TABLE {sql_table(shadow_lib, get_errors_table(no))} ("
             "SRC_RRN BIGINT NOT NULL PRIMARY KEY, SQL_STATE CHAR(5) NOT NULL, MESSAGE VARCHAR(1000) NOT NULL)")



def drop_work_tables(db: Connection, shadow_lib: str, no: int) -> None:

  for table in [get_map_table(no), get_changes_table(no), get_errors_table(no)]:
    if table_exists(db, shadow_lib, table):
      db.execute(f"DROP TABLE {sql_table(shadow_lib, table)}")



def table_exists(db: Connection, lib: str, name: str) -> bool:
  return (db.query_value("SELECT COUNT(*) FROM QSYS2.SYSTABLES WHERE SYSTEM_TABLE_SCHEMA = ? AND SYSTEM_TABLE_NAME = ?", [lib, name]) or 0) > 0



class Table_State:
  """Row of IRSTATE"""

  FIELDS = ['prod_lib', 'prod_file', 'phase', 'journal_lib', 'journal_name', 'journal_started',
            'receiver_lib', 'receiver_name', 'journal_sequence', 'start_time', 'copy_next_rrn', 'copy_end_rrn',
            'target_size', 'reuse_deleted', 'rows_copied', 'rows_applied', 'config_hash', 'message']


  def __init__(self, db: Connection, shadow_lib: str, no: int, prod_lib: str, prod_file: str):

    self.db = db
    self.shadow_lib = shadow_lib
    self.no = no
    self.exists = False

    self.prod_lib = prod_lib
    self.prod_file = prod_file
    self.phase = Phase.NEW
    self.journal_lib = ''
    self.journal_name = ''
    self.journal_started = False
    self.receiver_lib = ''
    self.receiver_name = ''
    self.journal_sequence = 0
    self.start_time = None
    self.copy_next_rrn = 1
    self.copy_end_rrn = 0
    # Size of the new table (incl. deleted records) after the last insert which has been completed
    self.target_size = 0
    self.reuse_deleted = False
    self.rows_copied = 0
    self.rows_applied = 0
    # Configuration of the table (columns, dependents, ...) the new table has been prepared with
    self.config_hash = ''
    self.message = ''


  def load(self) -> 'Table_State':

    rows = self.db.query(f"SELECT * FROM {sql_table(self.shadow_lib, C_STATE_TABLE)} WHERE TABLE_NO = ?", [self.no])
    if len(rows) == 0:
      return self

    row = rows[0]
    self.exists = True

    if row['prod_lib'].strip() != self.prod_lib or row['prod_file'].strip() != self.prod_file:
      raise Exception(f"Table {self.no} of the DB deployment was {row['prod_lib'].strip()}/{row['prod_file'].strip()}, "
                      f"but is configured as {self.prod_lib}/{self.prod_file}. Don't change the order of the tables in the configuration.")

    self.phase = Phase(row['phase'].strip())
    self.journal_lib = row['journal_lib'].strip()
    self.journal_name = row['journal_name'].strip()
    self.journal_started = row['journal_started'] == 'Y'
    self.receiver_lib = row['receiver_lib'].strip()
    self.receiver_name = row['receiver_name'].strip()
    self.journal_sequence = int(row['journal_sequence'])
    self.start_time = row['start_time']
    self.copy_next_rrn = int(row['copy_next_rrn'])
    self.copy_end_rrn = int(row['copy_end_rrn'])
    self.target_size = int(row['target_size'])
    self.reuse_deleted = row['reuse_deleted'] == 'Y'
    self.rows_copied = int(row['rows_copied'])
    self.rows_applied = int(row['rows_applied'])
    self.config_hash = row['config_hash'].strip()
    self.message = row['message'].strip()

    return self


  def get_values(self) -> list:

    values = []
    for field in self.FIELDS:
      value = getattr(self, field)
      if isinstance(value, Phase):
        value = value.value
      elif isinstance(value, bool):
        value = 'Y' if value else 'N'
      elif field == 'message':
        value = value[:2000]
      values.append(value)
    return values


  def save(self) -> None:

    table = sql_table(self.shadow_lib, C_STATE_TABLE)

    if self.exists:
      self.db.execute(f"UPDATE {table} SET {', '.join(f'{f.upper()} = ?' for f in self.FIELDS)}, UPDATE_TIME = CURRENT TIMESTAMP "
                      "WHERE TABLE_NO = ?", self.get_values() + [self.no])
      return

    self.db.execute(f"INSERT INTO {table} (TABLE_NO, {', '.join(f.upper() for f in self.FIELDS)}) "
                    f"VALUES (?, {', '.join('?' for _ in self.FIELDS)})", [self.no] + self.get_values())
    self.exists = True


  def check_config(self, table: dict) -> None:
    """The new table has been built and filled with the configuration of db-prepare"""

    if self.config_hash != get_config_hash(table):
      raise Db_Deployment_Exception(f"The configuration of {self.prod_lib}/{self.prod_file} (columns, dependents, library list) has changed "
                      "since db-prepare. Run db-prepare and db-copy again.")


  def set_phase(self, phase: Phase, message: str|None=None) -> None:
    self.phase = phase
    if message is not None:
      self.message = message
    self.save()



class Replaced_Object:
  """
  Row of IROBJECTS: a file which is replaced at the cut-over

  Attributes
  ----------
  kind : str
      table, index, lf, view
  origin : str
      deployment:  built from the source of the deployment
      generated:   SQL index, built from the SQL generated for the old index
      source:      logical file, built from the source member of the old one
      view:        view, created again from its generated SQL after the swap (it isn't moved)
  in_prod : bool
      An old version exists in production and is moved to the backup library
  """


  def __init__(self, no: int, seq: int, kind: str, origin: str, prod_lib: str, name: str, in_prod: bool,
               old_moved: bool=False, new_moved: bool=False):
    self.no = no
    self.seq = seq
    self.kind = kind
    self.origin = origin
    self.prod_lib = prod_lib
    self.name = name
    self.in_prod = in_prod
    self.old_moved = old_moved
    self.new_moved = new_moved


  def is_moved(self) -> bool:
    """Views are created again in production, all other objects are moved"""
    return self.kind != 'view'


  def __repr__(self) -> str:
    return f"{self.prod_lib}/{self.name} ({self.kind}, {self.origin})"



def save_objects(db: Connection, shadow_lib: str, no: int, objects: list[Replaced_Object]) -> None:

  table = sql_table(shadow_lib, C_OBJECTS_TABLE)
  db.execute(f"DELETE FROM {table} WHERE TABLE_NO = ?", [no])

  for o in objects:
    db.execute(f"INSERT INTO {table} (TABLE_NO, SEQ, KIND, ORIGIN, PROD_LIB, NAME, IN_PROD, OLD_MOVED, NEW_MOVED) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
               [no, o.seq, o.kind, o.origin, o.prod_lib, o.name, 'Y' if o.in_prod else 'N',
                'Y' if o.old_moved else 'N', 'Y' if o.new_moved else 'N'])



def load_objects(db: Connection, shadow_lib: str, no: int) -> list[Replaced_Object]:

  rows = db.query(f"SELECT * FROM {sql_table(shadow_lib, C_OBJECTS_TABLE)} WHERE TABLE_NO = ? ORDER BY SEQ", [no])

  return [Replaced_Object(no=no, seq=r['seq'], kind=r['kind'].strip(), origin=r['origin'].strip(), prod_lib=r['prod_lib'].strip(),
                          name=r['name'].strip(), in_prod=r['in_prod'] == 'Y',
                          old_moved=r['old_moved'] == 'Y', new_moved=r['new_moved'] == 'Y')
          for r in rows]



def save_object_moves(db: Connection, shadow_lib: str, o: Replaced_Object) -> None:
  db.execute(f"UPDATE {sql_table(shadow_lib, C_OBJECTS_TABLE)} SET OLD_MOVED = ?, NEW_MOVED = ? WHERE TABLE_NO = ? AND SEQ = ?",
             ['Y' if o.old_moved else 'N', 'Y' if o.new_moved else 'N', o.no, o.seq])
