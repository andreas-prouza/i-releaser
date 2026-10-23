"""
Step db-cutover: replaces the old table by the new one

1. Catch up with the changes while the users keep working
2. Lock the old table and its dependent files exclusively (the lock is held by the job of the connection)
3. Apply the remaining changes and compare the number of rows
4. Finish the new table: reuse of deleted records, identity columns, journaling, authorities
5. Swap: the old files are moved to the backup library, the new ones from the shadow library to production
6. Create the views again, set the owners
7. Release the locks

Running it again continues where it has stopped. If the swap fails, the objects moved so far are moved back.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from modules.db_deployment import catalog, objects, prepare, state, sync
from modules.db_deployment.connection import Connection, Db_Deployment_Exception, get_error_text, sql_table, sql_name
from modules.db_deployment.state import Table_State, Phase, Replaced_Object

if TYPE_CHECKING:
  from modules.meta_file import Meta_File



def cutover_table(db: Connection, meta_file: Meta_File, table: dict, settings: dict) -> list[Replaced_Object]:
  """
  Returns:
      list[Replaced_Object]: Objects which have been replaced
  """

  shadow_lib = objects.get_shadow_lib(meta_file)
  st = Table_State(db, shadow_lib, table['no'], table['lib'], table['name']).load()
  prod = f"{st.prod_lib}/{st.prod_file}"

  if st.phase == Phase.DONE:
    logging.info(f"{prod} has already been replaced")
    return state.load_objects(db, shadow_lib, st.no)

  if st.phase == Phase.FAILED:
    raise Db_Deployment_Exception(f"{prod} has failed: {st.message}. Prepare and copy it again.")

  if st.phase not in (Phase.COPIED, Phase.CUTOVER, Phase.SWAPPED):
    raise Db_Deployment_Exception(f"{prod} hasn't been copied yet (phase {st.phase.value}), run step db-copy first")

  if st.phase == Phase.COPIED:
    st.check_config(table)

  replaced = state.load_objects(db, shadow_lib, st.no)

  if st.phase == Phase.SWAPPED:
    finish_swap(db, meta_file, st, replaced)
    return replaced

  table_object = replaced[0]
  if table_object.old_moved:
    # Ended during the swap after the old table has been moved: nobody can change it anymore, so continue the swap
    logging.info(f"Continue the swap of {prod}")
    swap(db, meta_file, st, replaced)
    st.set_phase(Phase.SWAPPED)
    finish_swap(db, meta_file, st, replaced)
    return replaced

  move_back_old(db, meta_file, st, replaced)

  table_sync = sync.open_table_sync(db, shadow_lib, table, settings)
  table_sync.open()
  table_sync.catch_up()

  locked = [(o.prod_lib, o.name) for o in replaced if o.in_prod]
  lock(db, locked, int(settings['lock_wait_seconds']))

  try:
    st.set_phase(Phase.CUTOVER)

    table_sync.drain()
    table_sync.verify_counts()

    finish_new_table(db, st, table_sync, replaced)
    swap(db, meta_file, st, replaced)
    st.set_phase(Phase.SWAPPED)

    finish_swap(db, meta_file, st, replaced)

  finally:
    unlock(db, locked, objects.get_backup_lib(meta_file), replaced)

  return replaced



def lock(db: Connection, locked: list[tuple[str, str]], wait: int) -> None:
  """Exclusive lock of all files at once. Jobs with pseudo-closed cursors are asked to release them."""

  files = ' '.join(f"({lib}/{name} *FILE *EXCL)" for lib, name in locked)
  logging.info(f"Lock {', '.join(f'{l}/{n}' for l, n in locked)}, waiting up to {wait} seconds")

  try:
    db.qcmdexc(f"ALCOBJ OBJ({files}) WAIT({wait}) CONFLICT(*RQSRLS)")
  except Db_Deployment_Exception as e:
    holders = catalog.get_lock_holders(db, locked)
    raise Db_Deployment_Exception(f"The files can't be locked exclusively, users still work with them. "
                                  f"Locks held by: {', '.join(holders) or 'unknown'}. Run the cut-over again when they are free.") from e



def unlock(db: Connection, locked: list[tuple[str, str]], backup_lib: str, replaced: list[Replaced_Object]) -> None:
  """Releases the locks. A moved file is in the backup library now."""

  for lib, name in locked:
    o = next((o for o in replaced if o.prod_lib == lib and o.name == name), None)
    current_lib = backup_lib if o is not None and o.old_moved else lib
    db.qcmdexc(f"DLCOBJ OBJ(({current_lib}/{name} *FILE *EXCL))", ignore_errors=True)



def finish_new_table(db: Connection, st: Table_State, table_sync: sync.Table_Sync, replaced: list[Replaced_Object]) -> None:
  """Gives the new table the attributes of the old one, while it's still in the shadow library"""

  shadow_lib, name = st.shadow_lib, st.prod_file
  shadow = sql_table(shadow_lib, name)

  if st.reuse_deleted:
    db.qcmdexc(f"CHGPF FILE({shadow_lib}/{name}) REUSEDLT(*YES)")

  for column in table_sync.mapping.identity_columns:
    max_value = db.query_value(f"SELECT MAX({sql_name(column)}) FROM {shadow}")
    if max_value is not None:
      db.execute(f"ALTER TABLE {shadow} ALTER COLUMN {sql_name(column)} RESTART WITH {int(max_value) + 1}")

  info = catalog.get_object_info(db, st.prod_lib, name) or {}
  shadow_info = catalog.get_object_info(db, shadow_lib, name) or {}
  if info.get('journaled') == 'YES' and not st.journal_started and shadow_info.get('journaled') != 'YES':
    db.qcmdexc(f"STRJRNPF FILE({shadow_lib}/{name}) JRN({info['journal_library']}/{info['journal_name']}) "
               f"IMAGES({info.get('journal_images') or '*AFTER'}) OMTJRNE({info.get('omit_journal_entry') or '*NONE'})")

  for o in replaced:
    if o.is_moved():
      # New dependents get the authorities of the table
      ref_lib, ref_name = (o.prod_lib, o.name) if o.in_prod else (st.prod_lib, name)
      db.qcmdexc(f"GRTOBJAUT OBJ({shadow_lib}/{o.name}) OBJTYPE(*FILE) REFOBJ({ref_lib}/{ref_name}) REFOBJTYPE(*FILE)")



def swap(db: Connection, meta_file: Meta_File, st: Table_State, replaced: list[Replaced_Object]) -> None:
  """
  Moves the old files to the backup library, then the new ones to production.
  The old dependents are moved before the old table: as long as the old table is in production,
  the swap can be started again from the beginning.
  """

  shadow_lib = st.shadow_lib
  backup_lib = objects.get_backup_lib(meta_file)

  if not catalog.library_exists(db, backup_lib):
    db.qcmdexc(f"CRTLIB LIB({backup_lib}) TEXT('i-Releaser: backup of deployment {meta_file.id}')")

  moved = [o for o in replaced if o.is_moved()]
  old_order = [o for o in moved if o.kind != 'table'] + [o for o in moved if o.kind == 'table']
  done: list[tuple[str, Replaced_Object]] = []

  try:
    for o in old_order:
      if o.in_prod and not o.old_moved:
        move(db, o.prod_lib, o.name, backup_lib)
        o.old_moved = True
        state.save_object_moves(db, shadow_lib, o)
        done.append(('old', o))

    for o in moved:
      if not o.new_moved:
        move(db, shadow_lib, o.name, o.prod_lib)
        o.new_moved = True
        state.save_object_moves(db, shadow_lib, o)
        done.append(('new', o))

  except Exception as e:
    logging.error(f"Swap failed, move back: {get_error_text(e)}")
    undo_swap(db, shadow_lib, backup_lib, done)
    raise

  logging.info(f"{st.prod_lib}/{st.prod_file} has been replaced, the old files are in {backup_lib}")



def move(db: Connection, from_lib: str, name: str, to_lib: str) -> None:
  db.qcmdexc(f"MOVOBJ OBJ({from_lib}/{name}) OBJTYPE(*FILE) TOLIB({to_lib})")



def undo_swap(db: Connection, shadow_lib: str, backup_lib: str, done: list[tuple[str, Replaced_Object]]) -> None:

  for which, o in reversed(done):
    try:
      if which == 'new':
        move(db, o.prod_lib, o.name, shadow_lib)
        o.new_moved = False
      else:
        move(db, backup_lib, o.name, o.prod_lib)
        o.old_moved = False
      state.save_object_moves(db, shadow_lib, o)
    except Exception as e:
      raise Db_Deployment_Exception(f"Moving back {o} failed, check the objects in {o.prod_lib}, {shadow_lib} and {backup_lib}: "
                                    f"{get_error_text(e)}") from e



def move_back_old(db: Connection, meta_file: Meta_File, st: Table_State, replaced: list[Replaced_Object]) -> None:
  """A former cut-over has ended while moving the old dependents. As the old table is still in production, they are moved back."""

  backup_lib = objects.get_backup_lib(meta_file)

  for o in replaced:
    if o.old_moved and not o.new_moved:
      logging.info(f"Move {o} back from {backup_lib}")
      move(db, backup_lib, o.name, o.prod_lib)
      o.old_moved = False
      state.save_object_moves(db, st.shadow_lib, o)



def finish_swap(db: Connection, meta_file: Meta_File, st: Table_State, replaced: list[Replaced_Object]) -> None:
  """Views are created again over the new table, the new files get the owners of the old ones"""

  backup_lib = objects.get_backup_lib(meta_file)

  for o in replaced:
    if o.kind == 'view':
      path = prepare.get_view_source(meta_file, o)
      if not os.path.isfile(path):
        raise Db_Deployment_Exception(f"SQL of view {o.prod_lib}/{o.name} not found: {path}")
      db.qcmdexc(f"RUNSQLSTM SRCSTMF('{path}') COMMIT(*NONE) NAMING(*SQL) ERRLVL(20)")

  table_owner = None
  for o in replaced:
    if not o.is_moved():
      continue

    old_info = catalog.get_object_info(db, backup_lib, o.name if o.in_prod else st.prod_file) or {}
    owner = old_info.get('objowner')
    if o.kind == 'table':
      table_owner = owner
    owner = owner or table_owner

    new_info = catalog.get_object_info(db, o.prod_lib, o.name) or {}
    if owner and new_info.get('objowner') != owner:
      db.qcmdexc(f"CHGOBJOWN OBJ({o.prod_lib}/{o.name}) OBJTYPE(*FILE) NEWOWN({owner}) CUROWNAUT(*REVOKE)")

  st.set_phase(Phase.DONE, '')
