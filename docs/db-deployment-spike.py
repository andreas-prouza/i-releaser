"""
Checks on an IBM i whether the assumptions of the DB deployment hold (see docs/db-deployment.md)

Creates two test libraries, runs the checks and deletes the libraries again.
Uses the connection of etc/db_deployment.json for the given host.

    .venv/bin/python docs/db-deployment-spike.py --host localhost --lib IRSPIKE --rows 1000000

Each check prints PASS, FAIL or INFO. Please send the output if a check fails.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.realpath(f"{os.path.dirname(__file__)}/.."))

from modules.db_deployment import catalog, connection, journal, state
from modules.db_deployment.connection import sql_table



results = []



def check(title: str):
  """Runs the decorated function as a check: it returns an info text, or raises AssertionError/an exception"""

  def decorator(func):
    def run(*args):
      start = time.perf_counter()
      try:
        info = func(*args)
        status = 'PASS' if info is None or not str(info).startswith('INFO') else 'INFO'
      except AssertionError as e:
        status, info = 'FAIL', str(e)
      except Exception as e:
        status, info = 'FAIL', f"{type(e).__name__}: {connection.get_error_text(e)}"
      duration = time.perf_counter() - start
      results.append((status, title))
      print(f"{status:4}  {title} ({duration:.2f}s){': ' + str(info) if info else ''}", flush=True)
    return run
  return decorator



def timed(func, *args) -> float:
  start = time.perf_counter()
  func(*args)
  return time.perf_counter() - start



class Spike:


  def __init__(self, db: connection.Connection, db2: connection.Connection, lib: str, lib2: str, rows: int):
    self.db = db
    self.db2 = db2
    self.lib = lib
    self.lib2 = lib2
    self.rows = rows
    self.t = sql_table(lib, 'BIGT')
    self.s = sql_table(lib, 'SHADOWT')


  def setup(self) -> None:

    db = self.db
    for lib in [self.lib, self.lib2]:
      if catalog.library_exists(db, lib):
        raise Exception(f"Library {lib} exists already, use another one with --lib")
      db.qcmdexc(f"CRTLIB LIB({lib}) TEXT('i-Releaser DB deployment spike')")

    db.execute(f"CREATE TABLE {self.t} (ID BIGINT NOT NULL PRIMARY KEY, TEXT CHAR(50) NOT NULL, AMOUNT DECIMAL(11, 2))")
    db.execute(f"INSERT INTO {self.t} WITH N (I) AS (VALUES 1 UNION ALL SELECT I + 1 FROM N WHERE I < {self.rows}) "
               "SELECT I, 'Row ' CONCAT VARCHAR(I), I / 100.0 FROM N")
    db.execute(f"CREATE INDEX {sql_table(self.lib, 'BIGTI1')} ON {self.t} (TEXT)")
    db.execute(f"CREATE VIEW {sql_table(self.lib, 'BIGTV1')} AS SELECT ID, TEXT FROM {self.t}")


  def cleanup(self) -> None:
    for lib in [self.lib, self.lib2]:
      self.db.qcmdexc(f"ENDJRNPF FILE(*ALL) JRN({lib}/SPIKEJRN)", ignore_errors=True)
      self.db.qcmdexc(f"DLTJRN JRN({lib}/SPIKEJRN)", ignore_errors=True)
      self.db.qcmdexc(f"DLTJRNRCV JRNRCV({lib}/SPIKER*) DLTOPT(*IGNINQMSG)", ignore_errors=True)
      self.db.qcmdexc(f"DLTLIB LIB({lib})", ignore_errors=True)


  @check("1. Catalog queries of the DB deployment work")
  def catalog_queries(self):
    db, lib = self.db, self.lib
    table = catalog.get_table(db, lib, 'BIGT')
    assert table and table['table_type'] == 'T', f"get_table: {table}"
    columns = catalog.get_columns(db, lib, 'BIGT')
    assert [c['column_name'] for c in columns] == ['ID', 'TEXT', 'AMOUNT'], f"get_columns: {columns}"
    assert catalog.get_member_count(db, lib, 'BIGT') == 1
    assert catalog.get_size(db, lib, 'BIGT') == self.rows, f"get_size: {catalog.get_size(db, lib, 'BIGT')}"
    assert catalog.get_triggers(db, table) == []
    assert catalog.get_foreign_keys(db, lib, 'BIGT') == []
    dependents = catalog.get_dependents(db, lib, 'BIGT')
    kinds = {d['name']: d['kind'] for d in dependents}
    assert kinds == {'BIGTI1': 'index', 'BIGTV1': 'view'}, f"get_dependents: {dependents}"
    info = catalog.get_object_info(db, lib, 'BIGT')
    assert info and info['journaled'] == 'NO', f"get_object_info: {info}"
    reuse = catalog.get_reuse_deleted(db, lib, 'BIGT')
    assert reuse is True, f"get_reuse_deleted (DSPFD PHRUSE) of an SQL table: {reuse}"
    assert catalog.get_current_timestamp(db) is not None
    return f"object info: {info}"


  @check("2. RRN predicates use direct access (BETWEEN, =, IN) instead of a table scan")
  def rrn_access(self):
    db, t, middle = self.db, self.t, self.rows // 2
    scan = timed(db.query_value, f"SELECT COUNT(*) FROM {t} T WHERE AMOUNT < 0")
    between = timed(db.query_value, f"SELECT COUNT(*) FROM {t} T WHERE RRN(T) BETWEEN ? AND ?", [middle, middle + 999])
    equal = timed(db.query_value, f"SELECT COUNT(*) FROM {t} T WHERE RRN(T) = ?", [middle])
    in_list = timed(db.query_value, f"SELECT COUNT(*) FROM {t} T WHERE RRN(T) IN ({', '.join(str(middle + i * 7) for i in range(1000))})")
    text = f"table scan {scan:.3f}s, BETWEEN {between:.3f}s, = {equal:.3f}s, IN (1000 values) {in_list:.3f}s"
    assert max(between, equal, in_list) < scan / 5 or scan < 0.05, f"RRN access is not much faster than a table scan: {text}"
    return text


  @check("3. Insert ... ORDER BY into a table with REUSEDLT(*NO) appends in that order, size = rows + deleted rows")
  def ordered_insert(self):
    db, s = self.db, self.s
    db.execute(f"CREATE TABLE {s} (ID BIGINT NOT NULL PRIMARY KEY, TEXT CHAR(50) NOT NULL, AMOUNT DECIMAL(11, 2))")
    db.qcmdexc(f"CHGPF FILE({self.lib}/SHADOWT) REUSEDLT(*NO) SIZE(*NOMAX)")
    assert catalog.get_reuse_deleted(db, self.lib, 'SHADOWT') is False
    n = min(self.rows, 50000)
    db.execute(f"INSERT INTO {s} SELECT ID, TEXT, AMOUNT FROM {self.t} T WHERE RRN(T) <= {n} ORDER BY ID DESC")
    wrong = db.query_value(f"SELECT COUNT(*) FROM (SELECT RRN(S) AS R, ROW_NUMBER() OVER (ORDER BY ID DESC) AS N FROM {s} S) X WHERE R <> N")
    assert wrong == 0, f"{wrong} of {n} rows didn't get the RRN of their position in the insert"
    db.execute(f"DELETE FROM {s} S WHERE RRN(S) IN (1, 2, 3)")
    size = catalog.get_size(db, self.lib, 'SHADOWT')
    assert size == n, f"size after deleting 3 rows: {size}, expected {n}"
    db.execute(f"INSERT INTO {s} VALUES (-1, 'new', 0)")
    rrn = db.query_value(f"SELECT RRN(S) FROM {s} S WHERE ID = -1")
    assert rrn == n + 1, f"next insert got RRN {rrn}, expected {n + 1}"
    assert catalog.get_size(db, self.lib, 'SHADOWT') == n + 1


  @check("4. UPDATE ... SET (cols) = (subselect) and DELETE by RRN, IS NOT DISTINCT FROM, OVERRIDING SYSTEM VALUE")
  def statements(self):
    db, s = self.db, self.s
    count = db.execute(f"UPDATE {s} T SET (TEXT, AMOUNT) = (SELECT B.TEXT, B.AMOUNT FROM {self.t} B WHERE B.ID = T.ID) WHERE RRN(T) IN (10, 11)")
    assert count == 2, f"update changed {count} rows"
    count = db.execute(f"DELETE FROM {s} T WHERE RRN(T) IN (10, 11)")
    assert count == 2, f"delete changed {count} rows"
    assert db.query_value("SELECT COUNT(*) FROM SYSIBM.SYSDUMMY1 WHERE CAST(NULL AS INT) IS NOT DISTINCT FROM CAST(NULL AS INT)") == 1
    identity = sql_table(self.lib, 'IDENTT')
    db.execute(f"CREATE TABLE {identity} (ID BIGINT GENERATED ALWAYS AS IDENTITY, TEXT CHAR(10))")
    db.execute(f"INSERT INTO {identity} (ID, TEXT) OVERRIDING SYSTEM VALUE VALUES (4711, 'x')")
    db.execute(f"ALTER TABLE {identity} ALTER COLUMN ID RESTART WITH 4712")
    db.execute(f"INSERT INTO {identity} (TEXT) VALUES ('y')")
    assert db.query_value(f"SELECT MAX(ID) FROM {identity}") == 4712
    columns = catalog.get_columns(db, self.lib, 'IDENTT')
    assert columns[0]['is_identity'] == 'YES' and columns[0]['identity_generation'] == 'ALWAYS', f"identity column: {columns[0]}"
    return f"INFO identity column in SYSCOLUMNS: {columns[0]}"


  @check("5. DISPLAY_JOURNAL with object filter returns the RRNs of PT/UP/DL entries")
  def display_journal(self):
    db, lib = self.db, self.lib
    db.qcmdexc(f"CRTJRNRCV JRNRCV({lib}/SPIKER0001)")
    db.qcmdexc(f"CRTJRN JRN({lib}/SPIKEJRN) JRNRCV({lib}/SPIKER0001) MNGRCV(*SYSTEM) DLTRCV(*NO) RCVSIZOPT(*MAXOPT3)")

    # Journaling is started while another job has the table open
    cursor = self.db2.connection.cursor()
    cursor.execute(f"SELECT * FROM {self.t}")
    cursor.fetchmany(10)
    try:
      db.qcmdexc(f"STRJRNPF FILE({lib}/BIGT) JRN({lib}/SPIKEJRN) IMAGES(*AFTER) OMTJRNE(*OPNCLO)")
    finally:
      cursor.close()

    st = state.Table_State(db, lib, 1, lib, 'BIGT')
    st.journal_lib, st.journal_name = lib, 'SPIKEJRN'
    st.start_time = catalog.get_current_timestamp(db)
    st.save = lambda: None

    db.execute(f"INSERT INTO {self.t} VALUES (-5, 'journal', 0)")
    db.execute(f"UPDATE {self.t} T SET TEXT = 'updated' WHERE RRN(T) = 7")
    db.execute(f"DELETE FROM {self.t} T WHERE RRN(T) = 8")

    queued = set()
    reader = journal.Journal_Reader(db, st, batch_size=1000)
    count = reader.read(queued.update, lambda: None)
    assert {7, 8} <= queued and len(queued) == 3, f"queued RRNs: {queued} of {count} entries"

    db.execute(f"UPDATE {self.t} T SET TEXT = 'again' WHERE RRN(T) = 9")
    queued.clear()
    start = time.perf_counter()
    reader.read(queued.update, lambda: None)
    assert queued == {9}, f"second read (from saved position {st.receiver_name}/{st.journal_sequence}): {queued}"
    return f"INFO second read took {time.perf_counter() - start:.3f}s"


  @check("6. ALCOBJ *EXCL over QCMDEXC holds the lock in the server job, MOVOBJ of the locked file in the same job works")
  def lock_and_move(self):
    db, lib = self.db, self.lib
    db.qcmdexc(f"ALCOBJ OBJ(({lib}/SHADOWT *FILE *EXCL)) WAIT(10) CONFLICT(*RQSRLS)")
    holders = catalog.get_lock_holders(self.db2, [(lib, 'SHADOWT')])
    assert len(holders) > 0, "the lock isn't visible to another job"
    try:
      self.db2.execute(f"UPDATE {self.s} SET TEXT = 'locked' WHERE ID = 1")
      raise AssertionError("another job could change the locked table")
    except AssertionError:
      raise
    except Exception:
      pass
    db.qcmdexc(f"MOVOBJ OBJ({lib}/SHADOWT) OBJTYPE(*FILE) TOLIB({self.lib2})")
    db.qcmdexc(f"MOVOBJ OBJ({self.lib2}/SHADOWT) OBJTYPE(*FILE) TOLIB({lib})")
    db.qcmdexc(f"DLCOBJ OBJ(({lib}/SHADOWT *FILE *EXCL))")
    return f"INFO lock held by {holders}"


  @check("7. GENERATE_SQL into QTEMP/Q_GENSQL (unqualified and with CREATE OR REPLACE), DSPDBR, RENAME TO SYSTEM NAME")
  def generate_sql(self):
    db, lib = self.db, self.lib
    db.execute("CALL QSYS2.GENERATE_SQL(DATABASE_OBJECT_NAME => ?, DATABASE_OBJECT_LIBRARY_NAME => ?, DATABASE_OBJECT_TYPE => ?, "
               "DATABASE_SOURCE_FILE_NAME => 'Q_GENSQL', DATABASE_SOURCE_FILE_LIBRARY_NAME => 'QTEMP', DATABASE_SOURCE_FILE_MEMBER => 'Q_GENSQL', "
               "REPLACE_OPTION => '1', QUALIFIED_NAME_OPTION => ?, CREATE_OR_REPLACE_OPTION => ?)", ['BIGTI1', lib, 'INDEX', '1', '0'])
    index_sql = '\n'.join(r['srcdta'].rstrip() for r in db.query("SELECT SRCDTA FROM QTEMP.Q_GENSQL ORDER BY SRCSEQ"))
    assert 'CREATE INDEX' in index_sql.upper() and f'{lib}.' not in index_sql.upper().replace('"', ''), f"unqualified index SQL:\n{index_sql}"

    long_name = sql_table(lib, 'A_TABLE_WITH_A_LONG_NAME')
    db.execute(f"CREATE TABLE {long_name} (ID INT)")
    system_name = db.query_value("SELECT SYSTEM_TABLE_NAME FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = ? AND TABLE_NAME = 'A_TABLE_WITH_A_LONG_NAME'", [lib])
    db.execute(f"RENAME TABLE {long_name} TO SYSTEM NAME LONGNAME1")
    assert catalog.get_table(db, lib, 'LONGNAME1') is not None, f"rename of system name {system_name} failed"
    return f"INFO generated index SQL:\n{index_sql}"



def main() -> None:

  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('--host', default='localhost', help='connection in etc/db_deployment.json')
  parser.add_argument('--lib', default='IRSPIKE', help='test library (a second one gets the suffix 2), must not exist')
  parser.add_argument('--rows', type=int, default=1000000, help='rows of the test table')
  parser.add_argument('--keep', action='store_true', help="don't delete the test libraries")
  args = parser.parse_args()

  lib = args.lib.upper()
  config = connection.load_config()
  db = connection.connect(config, args.host)
  db2 = connection.connect(config, args.host)
  spike = Spike(db, db2, lib, f"{lib[:9]}2", args.rows)

  try:
    print(f"Create test table with {args.rows} rows in {lib} ...", flush=True)
    spike.setup()
    spike.catalog_queries()
    spike.rrn_access()
    spike.ordered_insert()
    spike.statements()
    spike.display_journal()
    spike.lock_and_move()
    spike.generate_sql()

  finally:
    if not args.keep:
      spike.cleanup()
    db2.close()
    db.close()

  failed = [title for status, title in results if status == 'FAIL']
  print(f"\n{len(results) - len(failed)} of {len(results)} checks passed")
  sys.exit(1 if failed else 0)



if __name__ == '__main__':
  main()
