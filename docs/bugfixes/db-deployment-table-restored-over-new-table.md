# Example deployment restores DB deployment tables over the new table

- **Status:** ready (Implemented. Open: the check on IBM i.)
- **Type:** bug (data loss)
- **Priority:** P0
- **Found:** 2026-10-23, code review


## Current situation

The documented DB deployment workflow runs `db-cutover` and then `perform-deployment` in the same stage.

* `scripts/examples/save_objects.py` saves **all** objects of the deployment into the save files, including the tables of the DB deployment.
* `scripts/examples/target_deployment.py` (`restore_objects_on_target`) restores the save file of each library, i.e. all its objects. It doesn't call `check_deploy_object`.
* Only `scripts/examples/backup_old_objects.py` skips them.

So after the cut-over has swapped in the new table with the production data, the restore replaces it with the table from the save file.
Depending on the restore, production data is lost or the restore fails.

`docs/db-deployment.md` currently warns about this.


## Requirements

1. `save_objects.py` doesn't save objects for which `db_objects.is_db_deployment_object(meta_file, obj)` is true (like `backup_old_objects.py`).
2. `target_deployment.py` calls `db_objects.check_deploy_object(meta_file, obj)` for each object and doesn't restore objects which have been replaced by the cut-over.
   It fails if the cut-over hasn't been done yet (behavior of `check_deploy_object`).
3. The restore uses standard commands instead of `PROUZALIB/IRSTLIB` (see [example scripts and configs](example-scripts-and-configs.md)).
4. Remove the warning from `docs/db-deployment.md`.


## Acceptance criteria

- [x] Test (without IBM i, commands recorded instead of run): for a deployment with a DB deployment table, neither the save nor the restore commands contain the table or its dependent files.
- [x] Test: `perform-deployment` before `db-cutover` fails with the error of `check_deploy_object`.
- [ ] Checked once on an IBM i with the test procedure of `docs/db-deployment.md`.


## Non-goals

* Changes of the DB deployment engine


## Decisions

* Is `scripts/obi.py` the reference? **The example scripts get the same checks, independent of `obi.py`.**
