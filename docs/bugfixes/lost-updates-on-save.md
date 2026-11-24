# Saving a deployment can overwrite newer changes

- **Status:** finished (2026-11-24; tested with `tests/test_stage_flow.py`, class `TestTransitions`)
- **Type:** bug
- **Priority:** P2
- **Found:** 2026-11-23, code review


## Current situation

Since [parallel stages overwrite each other's progress](parallel-stages-lost-update.md), a save only writes the columns which changed since loading (`saved_values`, `app_sqlite.update_changes`, see [technik.md](../technik.md#saving-a-deployment)). Some paths still overwrite newer values:

1. **Editing custom data writes every column.** `update_custom_data` sets `saved_values = None` and saves ([meta_file.py:981](../../modules/meta_file.py#L981)).
   Then all columns of `meta_files` are written ([meta_file_data.py:212](../../modules/db/meta_file_data.py#L212)), including `status` and `update_time` of the copy the request loaded.
   If a stage finishes or the deployment is canceled between loading and saving, the old status comes back.
2. **The snapshot is taken before the commit.** `save_meta_file` assigns `saved_values` before `conn.commit()` ([meta_file_data.py:397](../../modules/db/meta_file_data.py#L397); same in `stage_data`, `actions_data`, `deploy_object_data`).
   If the transaction fails (busy timeout, disk full, failing log file), the object thinks the values are stored, and later saves skip them.
3. **`refresh_state` doesn't update the snapshot.** It overwrites `status` from the database ([meta_file.py:292](../../modules/meta_file.py#L292)) but not `saved_values`, so the next save writes the refreshed value again, also over a change made after the refresh (e.g. a cancel).
4. **`_save_run_history` deletes a row and then updates it** ([meta_file_data.py:367](../../modules/db/meta_file_data.py#L367)): after `DELETE` for an empty log the `continue` is missing; it writes an empty log file and updates the deleted row.
5. **New objects without id are skipped silently**: `update_changes` with `id = None` runs `UPDATE … WHERE id = NULL` (e.g. for each new stage, `Stage.get_stage_from_dict` → `set_status` → `save_stage`, [stages.py:159](../../modules/stages.py#L159)).


## Requirements

1. `update_custom_data` writes only `custom_data` (it's already written by `change_custom_data` in a transaction; the save afterwards is only needed for `update_time`).
2. The snapshot (`saved_values`) is only taken over after a successful commit. Proposal: `save` collects the new snapshots and assigns them after `commit()`.
3. `refresh_state` also updates the snapshot of the values it overwrites.
4. `_save_run_history`: `continue` after the `DELETE`.
5. `update_changes` raises an exception for `id = None` (a programming error), and `get_stage_from_dict` doesn't save.
6. Long term: status is only written by atomic transitions, `saved_values` is removed (step 1 of the [core redesign](../features/core-redesign.md)).


## Acceptance criteria

- [x] Test: edit custom data while a stage finishes (the request copy is loaded before, saved after): the deployment keeps the new status.
- [x] Test: a save whose commit fails (simulated) is written completely by the next save.
- [x] Test: refresh, then a cancel by another connection, then save: the deployment stays `canceled`.
- [x] Test: an empty history log leaves no row and no file.


## Decisions (2026-11-24)

* Implemented together with step 1 of the [core redesign](../features/core-redesign.md): a save never writes the status of a deployment or a stage, only a transition does. That fixes items 1 and 3 for the status; `update_custom_data` writes only the time, its value is stored by `change_custom_data`.
* Requirement 2: if a save fails, all snapshots of the deployment are forgotten (`_forget_saved_values`), so the next save writes all columns. Simpler than taking them over after the commit, with the same result.


## Open questions

* None.
