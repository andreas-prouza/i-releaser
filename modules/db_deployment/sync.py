"""
Copies the rows of the old table to the new table and applies the changes from the journal

Each row of the old table is identified by its relative record number (RRN), each row of the new table as well.
The map table relates them, so a changed row can be found in the new table, with or without a unique key.

* The new table is only written by i-Releaser and doesn't reuse deleted records (REUSEDLT(*NO)).
  So inserted rows get the RRNs following the current size of the table, in the order of the insert.
  Each multi-row insert is verified. If the order hasn't been kept, the rows are inserted one by one.
* Rows are read once into a table in QTEMP, already converted to the new table.
  Both the new table and the map table are filled from there, so they always describe the same rows.
* Rows are read without locks. A change which is rolled back writes journal entries, so the row is applied again.
* A row which can't be applied (duplicate key, conversion error, ...) is recorded with its error and tried again later.
  A duplicate key may only exist for a while, as the rows are applied in RRN order and not in the order of their changes.
* Without commitment control, an insert may end in the middle. The size of the new table after the last
  completed insert is saved, so the rows behind it can be removed (repair) and inserted again.
"""
from __future__ import annotations

import logging
import time

from modules.db_deployment import catalog
from modules.db_deployment.connection import Connection, Db_Deployment_Exception, is_row_error, get_sqlstate, get_error_text, \
  sql_table, sql_name, sql_int_list
from modules.db_deployment.journal import Journal_Reader, Journal_Exception
from modules.db_deployment.mapping import Column_Mapping
from modules.db_deployment.state import Table_State, Phase, get_map_table, get_changes_table, get_errors_table, get_stage_table


# Maximum number of values in one IN list
C_IN_LIST_SIZE = 1000



class Verify_Exception(Db_Deployment_Exception):
  """Inserted rows didn't get the expected relative record numbers"""
  pass



class Progress:
  """Writes a progress message at most every interval seconds"""

  def __init__(self, interval: float):
    self.interval = interval
    self.start = time.monotonic()
    self.last = self.start

  def is_due(self) -> bool:
    now = time.monotonic()
    if now - self.last < self.interval:
      return False
    self.last = now
    return True

  def get_seconds(self) -> float:
    return max(time.monotonic() - self.start, 0.001)



class Table_Sync:


  def __init__(self, db: Connection, state: Table_State, mapping: Column_Mapping, settings: dict):

    self.db = db
    self.state = state
    self.mapping = mapping
    self.settings = settings

    self.prod = sql_table(state.prod_lib, state.prod_file)
    self.shadow = sql_table(state.shadow_lib, state.prod_file)
    self.map_table = sql_table(state.shadow_lib, get_map_table(state.no))
    self.changes_table = sql_table(state.shadow_lib, get_changes_table(state.no))
    self.errors_table = sql_table(state.shadow_lib, get_errors_table(state.no))
    self.stage_table = sql_table('QTEMP', get_stage_table(state.no))

    self.inserted = 0
    self.errors = 0
    self.order_warning = False


  #---------------------------------------------------------
  # Setup
  #---------------------------------------------------------

  def open(self) -> None:
    """Creates the table for the processed rows in QTEMP and removes rows of an insert which hasn't been completed"""

    try:
      self.db.execute(f"DROP TABLE {self.stage_table}")
    except Exception:
      pass

    self.db.execute(f"CREATE TABLE {self.stage_table} AS (SELECT CAST(NULL AS BIGINT) AS IR_SRC_RRN, {self.mapping.get_column_list()} "
                    f"FROM {self.shadow}) WITH NO DATA")
    self.repair()


  def test(self, rows: int=1000) -> None:
    """Converts the first rows and checks the statements, without changing the new table"""

    self.db.execute(f"INSERT INTO {self.stage_table} (IR_SRC_RRN, {self.mapping.get_column_list()}) "
                    f"SELECT RRN(P), {self.mapping.get_expression_list()} FROM {self.prod} P FETCH FIRST {int(rows)} ROWS ONLY")
    self.db.execute(f"{self.get_insert_sql()} WHERE 1 = 0")
    self.db.execute(f"INSERT INTO {self.map_table} (SRC_RRN, TGT_RRN) SELECT IR_SRC_RRN, IR_SRC_RRN FROM {self.stage_table} WHERE 1 = 0")
    self.clear_stage()


  def get_size(self) -> int:
    return catalog.get_size(self.db, self.state.shadow_lib, self.state.prod_file)


  def repair(self) -> None:
    """Removes the rows behind the last completed insert, from the new table and the map table"""

    committed = self.state.target_size
    size = self.get_size()

    if size <= committed:
      return

    removed = self.db.execute(f"DELETE FROM {self.shadow} T WHERE RRN(T) > ?", [committed])
    self.db.execute(f"DELETE FROM {self.map_table} WHERE TGT_RRN > ?", [committed])
    logging.info(f"Removed {removed} rows of an insert which hasn't been completed from {self.shadow} (records after {committed})")


  def clear_stage(self) -> None:
    self.db.execute(f"DELETE FROM {self.stage_table}")


  def get_staged(self) -> list[int]:
    return [int(r['ir_src_rrn']) for r in self.db.query(f"SELECT IR_SRC_RRN FROM {self.stage_table} ORDER BY IR_SRC_RRN")]


  def get_insert_sql(self) -> str:
    overriding = ' OVERRIDING SYSTEM VALUE' if self.mapping.overriding else ''
    return (f"INSERT INTO {self.shadow} ({self.mapping.get_column_list()}){overriding} "
            f"SELECT {self.mapping.get_column_list()} FROM {self.stage_table}")


  #---------------------------------------------------------
  # Read rows of the old table
  #---------------------------------------------------------

  def stage_range(self, first: int, last: int) -> None:
    """Reads the rows of an RRN range of the old table. Rows which can't be converted are recorded as errors."""

    try:
      self.db.execute(f"INSERT INTO {self.stage_table} (IR_SRC_RRN, {self.mapping.get_column_list()}) "
                      f"SELECT RRN(P), {self.mapping.get_expression_list()} FROM {self.prod} P WHERE RRN(P) BETWEEN ? AND ?",
                      [first, last])
      return

    except Exception as e:
      if not is_row_error(e):
        raise
      error = e

    if first == last:
      self.add_error(first, error)
      return

    # Rows read before the error may have been inserted
    self.db.execute(f"DELETE FROM {self.stage_table} WHERE IR_SRC_RRN BETWEEN ? AND ?", [first, last])
    middle = (first + last) // 2
    self.stage_range(first, middle)
    self.stage_range(middle + 1, last)


  def stage_rrns(self, rrns: list[int]) -> None:
    """Reads the rows with these RRNs of the old table. Rows which can't be converted are recorded as errors."""

    if len(rrns) == 0:
      return

    try:
      self.db.execute(f"INSERT INTO {self.stage_table} (IR_SRC_RRN, {self.mapping.get_column_list()}) "
                      f"SELECT RRN(P), {self.mapping.get_expression_list()} FROM {self.prod} P WHERE RRN(P) IN ({sql_int_list(rrns)})")
      return

    except Exception as e:
      if not is_row_error(e):
        raise
      error = e

    if len(rrns) == 1:
      self.add_error(rrns[0], error)
      return

    self.db.execute(f"DELETE FROM {self.stage_table} WHERE IR_SRC_RRN IN ({sql_int_list(rrns)})")
    middle = len(rrns) // 2
    self.stage_rrns(rrns[:middle])
    self.stage_rrns(rrns[middle:])


  #---------------------------------------------------------
  # Write rows to the new table
  #---------------------------------------------------------

  def insert_rows(self, rrns: list[int]) -> None:
    """
    Inserts staged rows into the new table and the map table.

    Args:
        rrns: all staged RRNs between the first and the last one, sorted
    """

    if len(rrns) == 0:
      return

    error = None

    try:
      self.insert_block(rrns[0], rrns[-1], len(rrns))
      return

    except Verify_Exception as e:
      if len(rrns) == 1:
        raise
      if not self.order_warning:
        logging.warning(f"{e}. The rows are inserted in smaller parts.")
        self.order_warning = True

    except Exception as e:
      if not is_row_error(e):
        raise
      error = e

    self.repair()

    if len(rrns) == 1:
      self.add_error(rrns[0], error)
      return

    middle = len(rrns) // 2
    self.insert_rows(rrns[:middle])
    self.insert_rows(rrns[middle:])


  def insert_block(self, first: int, last: int, count: int) -> None:
    """Inserts the staged rows from first to last RRN and maps them"""

    st = self.state
    base = self.get_size()

    # Rows behind this size are removed again, if the insert doesn't complete
    st.target_size = base
    st.save()

    inserted = self.db.execute(f"{self.get_insert_sql()} WHERE IR_SRC_RRN BETWEEN ? AND ? ORDER BY IR_SRC_RRN", [first, last])
    size = self.get_size()

    if inserted != count or size != base + count:
      raise Verify_Exception(f"Insert of {count} rows into {self.shadow} added {inserted} rows, its size changed from {base} to {size}. "
                             "The new table must not be changed by others and must not reuse deleted records")

    self.db.execute(f"INSERT INTO {self.map_table} (SRC_RRN, TGT_RRN) "
                    "SELECT IR_SRC_RRN, CAST(? AS BIGINT) + ROW_NUMBER() OVER (ORDER BY IR_SRC_RRN) "
                    f"FROM {self.stage_table} WHERE IR_SRC_RRN BETWEEN ? AND ?", [base, first, last])

    if count > 1 and self.settings['verify_inserts'] and len(self.mapping.compare_columns) > 0:
      matched = self.db.query_value(self.get_verify_sql(), [base + 1, base + count, base, first, last])
      if matched != count:
        raise Verify_Exception(f"Only {matched} of {count} rows inserted into {self.shadow} have the expected relative record number")

    st.target_size = base + count
    st.save()
    self.inserted += count


  def get_verify_sql(self) -> str:
    """Counts the inserted rows which equal the staged ones at their expected RRN"""

    columns = self.mapping.compare_columns
    condition = ' AND '.join(f"A.{sql_name(c)} IS NOT DISTINCT FROM B.{sql_name(c)}" for c in columns)

    return (f"SELECT COUNT(*) FROM "
            f"(SELECT RRN(T) AS IR_RRN, {', '.join('T.' + sql_name(c) for c in columns)} FROM {self.shadow} T WHERE RRN(T) BETWEEN ? AND ?) A "
            f"JOIN (SELECT CAST(? AS BIGINT) + ROW_NUMBER() OVER (ORDER BY IR_SRC_RRN) AS IR_RRN, {', '.join(sql_name(c) for c in columns)} "
            f"FROM {self.stage_table} WHERE IR_SRC_RRN BETWEEN ? AND ?) B "
            f"ON A.IR_RRN = B.IR_RRN AND {condition}")


  def update_rows(self, rrns: list[int], mapped: dict[int, int]) -> list[int]:
    """
    Updates rows of the new table with the staged rows.

    Returns:
        list[int]: RRNs (old table) which couldn't be updated. They are deleted and inserted again.
    """

    if len(rrns) == 0 or len(self.mapping.update_columns) == 0:
      return []

    targets = [mapped[r] for r in rrns]
    columns = ', '.join(sql_name(c) for c in self.mapping.update_columns)
    values = ', '.join('S.' + sql_name(c) for c in self.mapping.update_columns)

    try:
      count = self.db.execute(f"UPDATE {self.shadow} T SET ({columns}) = "
                              f"(SELECT {values} FROM {self.stage_table} S JOIN {self.map_table} M ON M.SRC_RRN = S.IR_SRC_RRN "
                              f"WHERE M.TGT_RRN = RRN(T)) WHERE RRN(T) IN ({sql_int_list(targets)})")

    except Exception as e:
      if not is_row_error(e):
        raise
      if len(rrns) == 1:
        logging.debug(f"Row {rrns[0]} of {self.prod} can't be updated ({get_error_text(e)}), it is inserted again")
        return rrns
      middle = len(rrns) // 2
      return self.update_rows(rrns[:middle], mapped) + self.update_rows(rrns[middle:], mapped)

    if count == len(rrns):
      return []

    # A row of the new table may have been deleted while its map entry still exists (a step ended in between)
    existing = {int(r['rrn']) for r in self.db.query(f"SELECT RRN(T) AS RRN FROM {self.shadow} T WHERE RRN(T) IN ({sql_int_list(targets)})")}
    return [r for r in rrns if mapped[r] not in existing]


  def delete_rows(self, rrns: list[int], mapped: dict[int, int]) -> None:
    """Deletes rows from the new table, then from the map table"""

    if len(rrns) == 0:
      return

    self.db.execute(f"DELETE FROM {self.shadow} T WHERE RRN(T) IN ({sql_int_list(mapped[r] for r in rrns)})")
    self.db.execute(f"DELETE FROM {self.map_table} WHERE SRC_RRN IN ({sql_int_list(rrns)})")


  def add_error(self, rrn: int, e: Exception|None) -> None:

    sqlstate = get_sqlstate(e) if e is not None else ''
    message = get_error_text(e)[:1000] if e is not None else ''

    self.db.execute(f"DELETE FROM {self.errors_table} WHERE SRC_RRN = ?", [rrn])
    self.db.execute(f"INSERT INTO {self.errors_table} (SRC_RRN, SQL_STATE, MESSAGE) VALUES (?, ?, ?)", [rrn, sqlstate or '', message])
    self.errors += 1
    logging.warning(f"Row {rrn} of {self.prod} can't be applied: {sqlstate} {message}")

    if self.errors > int(self.settings['max_errors']):
      raise Db_Deployment_Exception(f"More than {self.settings['max_errors']} rows of {self.prod} can't be applied. "
                                    f"Check the column expressions; the errors are in {self.errors_table}")


  #---------------------------------------------------------
  # Copy
  #---------------------------------------------------------

  def copy(self) -> None:
    """Copies all rows which existed at the start. Rows added later come from the journal."""

    st = self.state

    if st.phase == Phase.PREPARED:
      st.copy_next_rrn = 1
      st.copy_end_rrn = catalog.get_size(self.db, st.prod_lib, st.prod_file)
      st.set_phase(Phase.COPYING)

    if st.phase != Phase.COPYING:
      return

    batch_size = int(self.settings['batch_size'])
    progress = Progress(float(self.settings['progress_interval_seconds']))
    start_rrn = st.copy_next_rrn

    logging.info(f"Copy {self.prod} to {self.shadow}: records {st.copy_next_rrn} to {st.copy_end_rrn}")

    while st.copy_next_rrn <= st.copy_end_rrn:

      first = st.copy_next_rrn
      last = min(first + batch_size - 1, st.copy_end_rrn)

      inserted = self.inserted
      self.clear_stage()
      self.stage_range(first, last)
      self.insert_rows(self.get_staged())

      st.copy_next_rrn = last + 1
      st.rows_copied += self.inserted - inserted
      st.save()

      if progress.is_due():
        done = st.copy_next_rrn - start_rrn
        rate = done / progress.get_seconds()
        remaining = (st.copy_end_rrn - st.copy_next_rrn + 1) / rate if rate > 0 else 0
        logging.info(f"Copy {self.prod}: {st.copy_next_rrn - 1} of {st.copy_end_rrn} records ({(st.copy_next_rrn - 1) * 100 / max(st.copy_end_rrn, 1):.1f}%), "
                     f"{st.rows_copied} rows copied, {rate:.0f} records/s, about {remaining / 60:.0f} minutes remaining")

    self.clear_stage()
    st.set_phase(Phase.COPIED)
    logging.info(f"Copy of {self.prod} finished: {st.rows_copied} rows")


  #---------------------------------------------------------
  # Journal changes
  #---------------------------------------------------------

  def read_journal(self) -> int:
    """Queues the RRNs of the rows which have changed since the last read. Returns the number of journal entries."""

    try:
      return Journal_Reader(self.db, self.state, int(self.settings['journal_batch_size'])).read(self.queue_rrns, self.clear_all)
    except Journal_Exception as e:
      self.state.set_phase(Phase.FAILED, str(e))
      raise


  def queue_rrns(self, rrns: set[int]) -> None:

    rrns = sorted(rrns)

    for i in range(0, len(rrns), C_IN_LIST_SIZE):
      values = ', '.join(f"({int(r)})" for r in rrns[i:i + C_IN_LIST_SIZE])
      self.db.execute(f"INSERT INTO {self.changes_table} (SRC_RRN) SELECT V.SRC_RRN FROM (VALUES {values}) V (SRC_RRN) "
                      f"WHERE NOT EXISTS (SELECT 1 FROM {self.changes_table} C WHERE C.SRC_RRN = V.SRC_RRN)")


  def clear_all(self) -> None:
    """The old table has been cleared"""

    self.db.execute(f"DELETE FROM {self.shadow}")
    self.db.execute(f"DELETE FROM {self.map_table}")
    self.db.execute(f"DELETE FROM {self.changes_table}")
    self.db.execute(f"DELETE FROM {self.errors_table}")
    self.state.target_size = self.get_size()
    self.state.save()


  def retry_errors(self) -> None:
    """Rows which couldn't be applied are queued again"""

    self.db.execute(f"INSERT INTO {self.changes_table} (SRC_RRN) SELECT E.SRC_RRN FROM {self.errors_table} E "
                    f"WHERE NOT EXISTS (SELECT 1 FROM {self.changes_table} C WHERE C.SRC_RRN = E.SRC_RRN)")


  def get_backlog(self) -> int:
    return int(self.db.query_value(f"SELECT COUNT(*) FROM {self.changes_table}") or 0)


  def get_error_count(self) -> int:
    return int(self.db.query_value(f"SELECT COUNT(*) FROM {self.errors_table}") or 0)


  def get_errors(self, count: int=20) -> list[dict]:
    return self.db.query(f"SELECT SRC_RRN, SQL_STATE, MESSAGE FROM {self.errors_table} ORDER BY SRC_RRN FETCH FIRST {int(count)} ROWS ONLY")


  def apply_changes(self) -> int:
    """Applies all queued rows. Returns their number."""

    total = 0
    batch_size = int(self.settings['apply_batch_size'])
    progress = Progress(float(self.settings['progress_interval_seconds']))

    while True:

      rows = self.db.query(f"SELECT SRC_RRN FROM {self.changes_table} ORDER BY SRC_RRN FETCH FIRST {batch_size} ROWS ONLY")
      if len(rows) == 0:
        break

      rrns = [int(r['src_rrn']) for r in rows]
      self.apply_batch(rrns)
      total += len(rrns)

      if progress.is_due():
        logging.info(f"Apply changes of {self.prod}: {total} rows applied, {self.get_backlog()} waiting")

    return total


  def apply_batch(self, rrns: list[int]) -> None:
    """
    Makes the rows of the new table equal to the current rows of the old table:
    * Row doesn't exist anymore: deleted
    * Row exists in both: updated
    * Row is new: inserted
    * Row can't be updated (e.g. it takes over a key value of another row of the batch): deleted and inserted
    """

    in_list = sql_int_list(rrns)

    self.db.execute(f"DELETE FROM {self.errors_table} WHERE SRC_RRN IN ({in_list})")
    self.clear_stage()
    self.stage_rrns(rrns)

    staged = self.get_staged()
    mapped = {int(r['src_rrn']): int(r['tgt_rrn'])
              for r in self.db.query(f"SELECT SRC_RRN, TGT_RRN FROM {self.map_table} WHERE SRC_RRN IN ({in_list})")}

    staged_set = set(staged)
    self.delete_rows([r for r in mapped if r not in staged_set], mapped)

    update = [r for r in staged if r in mapped]
    failed = self.update_rows(update, mapped)
    self.delete_rows(failed, mapped)

    failed_set = set(failed)
    updated = [r for r in update if r not in failed_set]
    for i in range(0, len(updated), C_IN_LIST_SIZE):
      self.db.execute(f"DELETE FROM {self.stage_table} WHERE IR_SRC_RRN IN ({sql_int_list(updated[i:i + C_IN_LIST_SIZE])})")

    self.insert_rows([r for r in staged if r not in mapped or r in failed_set])

    self.db.execute(f"DELETE FROM {self.changes_table} WHERE SRC_RRN IN ({in_list})")
    self.state.rows_applied += len(rrns)
    self.state.save()


  def catch_up(self) -> None:
    """
    Applies the changes until no more than catch_up_threshold rows wait.
    The users keep on working, so new changes may arrive while applying.
    """

    threshold = int(self.settings['catch_up_threshold'])
    max_cycles = int(self.settings['catch_up_max_cycles'])

    for cycle in range(1, max_cycles + 1):

      self.retry_errors()
      entries = self.read_journal()
      backlog = self.get_backlog()
      logging.info(f"Catch up {self.prod}, cycle {cycle}: {entries} new journal entries, {backlog} rows to apply")

      if backlog == 0:
        break

      self.apply_changes()

      if backlog <= threshold:
        break

    else:
      logging.warning(f"{self.prod} hasn't caught up after {max_cycles} cycles: changes come in faster than they are applied")

    errors = self.get_error_count()
    if errors > 0:
      logging.warning(f"{errors} rows of {self.prod} can't be applied yet (see {self.errors_table}): {self.get_errors(5)}")


  def drain(self) -> None:
    """
    Applies all remaining changes, while the old table is locked.
    Rows which still can't be applied (e.g. duplicate keys in the old data) end the cut-over.
    """

    previous_errors = None

    while True:

      entries = self.read_journal()
      self.retry_errors()
      applied = self.apply_changes()
      errors = self.get_error_count()
      logging.info(f"Final apply of {self.prod}: {entries} new journal entries, {applied} rows applied, {errors} rows with errors")

      if entries == 0 and self.get_backlog() == 0 and (errors == 0 or errors == previous_errors):
        break

      previous_errors = errors

    if errors > 0:
      details = '\n'.join(f"  RRN {r['src_rrn']}: {r['sql_state']} {r['message']}" for r in self.get_errors())
      raise Db_Deployment_Exception(f"{errors} rows of {self.prod} can't be applied to the new table (see {self.errors_table}):\n{details}")


  def verify_counts(self) -> None:

    prod_rows = catalog.get_row_count(self.db, self.prod)
    shadow_rows = catalog.get_row_count(self.db, self.shadow)
    map_rows = catalog.get_row_count(self.db, self.map_table)

    if not (prod_rows == shadow_rows == map_rows):
      raise Db_Deployment_Exception(f"Number of rows differs: {self.prod} {prod_rows}, {self.shadow} {shadow_rows}, {self.map_table} {map_rows}")

    logging.info(f"{self.prod} and {self.shadow} have {prod_rows} rows")



def open_table_sync(db: Connection, shadow_lib: str, table: dict, settings: dict) -> Table_Sync:
  """Table_Sync for a configured table, with the mapping of its columns"""

  st = Table_State(db, shadow_lib, table['no'], table['lib'], table['name']).load()

  mapping = Column_Mapping(catalog.get_columns(db, st.prod_lib, st.prod_file),
                           catalog.get_columns(db, shadow_lib, st.prod_file),
                           table.get('columns'))

  return Table_Sync(db, st, mapping, settings)



def copy_table(db: Connection, shadow_lib: str, table: dict, settings: dict) -> None:
  """Step db-copy for one table: copy (or continue it), then catch up with the changes made meanwhile"""

  st = Table_State(db, shadow_lib, table['no'], table['lib'], table['name']).load()
  prod = f"{st.prod_lib}/{st.prod_file}"

  if st.phase in (Phase.CUTOVER, Phase.SWAPPED, Phase.DONE):
    logging.info(f"{prod} is already in phase {st.phase.value}, nothing to copy")
    return

  if st.phase == Phase.FAILED:
    raise Db_Deployment_Exception(f"{prod} has failed: {st.message}. Prepare it again (step db-prepare).")

  if st.phase == Phase.NEW:
    raise Db_Deployment_Exception(f"{prod} hasn't been prepared yet (step db-prepare)")

  st.check_config(table)

  sync = open_table_sync(db, shadow_lib, table, settings)
  sync.open()
  sync.copy()
  sync.catch_up()
