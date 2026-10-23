"""
Reads the journal entries of the old table (QSYS2.DISPLAY_JOURNAL) since the last read

Only the relative record numbers of changed rows are used, the images of the rows are not needed.
So any journal setting works (IMAGES, MINENTDTA, ...).

The position (receiver and sequence number of the last entry) is saved in the state,
so a read continues where the last one has ended. Reading an entry twice does no harm.
"""
from __future__ import annotations

import logging
from typing import Callable

from modules.db_deployment.connection import Connection, Db_Deployment_Exception
from modules.db_deployment.state import Table_State


# Record entries without a relative record number
C_IGNORED_R_TYPES = {'IL'}

# File entries which don't change the rows: open, close, saved, start of save, force, format info,
# journaling started, access path entries, deleted record count, member changed
C_IGNORED_F_TYPES = {'OP', 'CL', 'MS', 'SS', 'FD', 'FI', 'JM', 'PD', 'PM', 'PN', 'DE', 'CB'}

# Member cleared (CLRPFM)
C_CLEARED_F_TYPES = {'CR'}

ROW = 'row'
IGNORE = 'ignore'
CLEAR = 'clear'
FAIL = 'fail'



class Journal_Exception(Db_Deployment_Exception):
  """The table has been changed in a way which can't be followed (e.g. RGZPFM, ALTER TABLE)"""
  pass



def classify(journal_code: str, entry_type: str) -> str:
  """
  Returns:
      str: row     a row has changed
           ignore  doesn't change rows
           clear   all rows have been deleted
           fail    the relative record numbers or the structure have changed (e.g. reorganize, alter table)
  """

  code = (journal_code or '').strip()
  entry_type = (entry_type or '').strip()

  if code == 'R':
    return IGNORE if entry_type in C_IGNORED_R_TYPES else ROW

  if code == 'F':
    if entry_type in C_CLEARED_F_TYPES:
      return CLEAR
    if entry_type in C_IGNORED_F_TYPES:
      return IGNORE
    return FAIL

  if code == 'D':
    return FAIL

  return IGNORE



class Journal_Reader:


  def __init__(self, db: Connection, state: Table_State, batch_size: int):
    self.db = db
    self.state = state
    self.batch_size = batch_size


  def fetch(self) -> list[dict]:
    """Next entries of the table after the saved position (or since the start time)"""

    st = self.state
    columns = "SEQUENCE_NUMBER, JOURNAL_CODE, JOURNAL_ENTRY_TYPE, COUNT_OR_RRN, RECEIVER_LIBRARY, RECEIVER_NAME"
    object_filter = "JOURNAL_CODES => 'R F D', OBJECT_LIBRARY => ?, OBJECT_NAME => ?, OBJECT_OBJTYPE => '*FILE', OBJECT_MEMBER => '*ALL'"

    if st.receiver_name == '':
      return self.db.query(f"SELECT {columns} FROM TABLE(QSYS2.DISPLAY_JOURNAL(JOURNAL_LIBRARY => ?, JOURNAL_NAME => ?, "
                           f"STARTING_RECEIVER_NAME => '*CURCHAIN', STARTING_TIMESTAMP => ?, {object_filter})) X "
                           "FETCH FIRST ? ROWS ONLY",
                           [st.journal_lib, st.journal_name, st.start_time, st.prod_lib, st.prod_file, self.batch_size])

    # The saved entry is read again (it exists for sure), so only the ones after it are used
    return self.db.query(f"SELECT {columns} FROM TABLE(QSYS2.DISPLAY_JOURNAL(JOURNAL_LIBRARY => ?, JOURNAL_NAME => ?, "
                         f"STARTING_RECEIVER_LIBRARY => ?, STARTING_RECEIVER_NAME => ?, STARTING_SEQUENCE => ?, {object_filter})) X "
                         "WHERE SEQUENCE_NUMBER > ? FETCH FIRST ? ROWS ONLY",
                         [st.journal_lib, st.journal_name, st.receiver_lib, st.receiver_name, st.journal_sequence,
                          st.prod_lib, st.prod_file, st.journal_sequence, self.batch_size])


  def read(self, on_rows: Callable[[set[int]], None], on_clear: Callable[[], None]) -> int:
    """
    Reads all new entries.

    Args:
        on_rows: queues the relative record numbers of changed rows
        on_clear: all rows of the table have been deleted

    Returns:
        int: Number of read entries

    Raises:
        Journal_Exception: The table has been changed in a way which can't be followed
    """

    st = self.state
    total = 0

    while True:

      try:
        entries = self.fetch()
      except Exception as e:
        raise Db_Deployment_Exception(f"Journal {st.journal_lib}/{st.journal_name} can't be read from receiver "
                                      f"{st.receiver_lib}/{st.receiver_name} sequence {st.journal_sequence}. "
                                      f"If a journal receiver has been deleted, prepare and copy the table again: {e}") from e

      if len(entries) == 0:
        break

      rrns: set[int] = set()

      for entry in entries:

        kind = classify(entry['journal_code'], entry['journal_entry_type'])

        if kind == ROW:
          rrn = int(entry['count_or_rrn'] or 0)
          if rrn > 0:
            rrns.add(rrn)

        elif kind == CLEAR:
          logging.info(f"{st.prod_lib}/{st.prod_file} has been cleared (journal sequence {entry['sequence_number']})")
          rrns = set()
          on_clear()

        elif kind == FAIL:
          on_rows(rrns)
          raise Journal_Exception(f"Journal entry {entry['journal_code']}/{entry['journal_entry_type']} (sequence {entry['sequence_number']}): "
                                  f"{st.prod_lib}/{st.prod_file} has been changed in a way which can't be followed "
                                  "(e.g. reorganized, initialized or altered). Prepare and copy it again.")

        st.receiver_lib = entry['receiver_library'].strip()
        st.receiver_name = entry['receiver_name'].strip()
        st.journal_sequence = int(entry['sequence_number'])

      on_rows(rrns)
      st.save()
      total += len(entries)

      if len(entries) < self.batch_size:
        break

    return total
