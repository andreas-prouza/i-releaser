"""
Step db-cleanup: removes the shadow library of a deployment

Journaling which has been started by i-Releaser is ended: for the old table in the backup library after the cut-over,
for the table in production if the DB deployment is given up before the cut-over.
The old tables stay in the backup library.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from modules.db_deployment import catalog, objects, state
from modules.db_deployment.connection import Connection, Db_Deployment_Exception
from modules.db_deployment.state import Table_State, Phase

if TYPE_CHECKING:
  from modules.meta_file import Meta_File



def cleanup(db: Connection, meta_file: Meta_File, tables: list[dict]) -> None:

  shadow_lib = objects.get_shadow_lib(meta_file)
  backup_lib = objects.get_backup_lib(meta_file)

  if not catalog.library_exists(db, shadow_lib):
    logging.info(f"Shadow library {shadow_lib} doesn't exist (anymore)")
    return

  states = []
  if state.table_exists(db, shadow_lib, state.C_STATE_TABLE):
    states = [Table_State(db, shadow_lib, t['no'], t['lib'], t['name']).load() for t in tables]

  unfinished = [f"{st.prod_lib}/{st.prod_file}" for st in states if st.phase in (Phase.CUTOVER, Phase.SWAPPED)]
  if len(unfinished) > 0:
    raise Db_Deployment_Exception(f"The cut-over of {', '.join(unfinished)} hasn't been finished. Run step db-cutover again first.")

  for st in states:
    if not st.exists or not st.journal_started:
      continue

    lib = backup_lib if st.phase == Phase.DONE else st.prod_lib
    info = catalog.get_object_info(db, lib, st.prod_file) or {}

    if info.get('journaled') == 'YES' and info.get('journal_library') == shadow_lib:
      db.qcmdexc(f"ENDJRNPF FILE({lib}/{st.prod_file}) JRN({shadow_lib}/{state.C_JOURNAL})")

    if st.phase != Phase.DONE:
      logging.warning(f"{st.prod_lib}/{st.prod_file} has not been replaced (phase {st.phase.value}), the DB deployment is given up")

  if catalog.object_exists(db, shadow_lib, state.C_JOURNAL, '*JRN'):
    # End journaling of files which are still journaled to it (e.g. a table which isn't configured anymore)
    db.qcmdexc(f"ENDJRNPF FILE(*ALL) JRN({shadow_lib}/{state.C_JOURNAL})", ignore_errors=True)
    db.qcmdexc(f"DLTJRN JRN({shadow_lib}/{state.C_JOURNAL})")
    db.qcmdexc(f"DLTJRNRCV JRNRCV({shadow_lib}/{state.C_JOURNAL_RECEIVER[:5]}*) DLTOPT(*IGNINQMSG)", ignore_errors=True)

  db.qcmdexc(f"DLTLIB LIB({shadow_lib})")
  logging.info(f"Shadow library {shadow_lib} deleted")
