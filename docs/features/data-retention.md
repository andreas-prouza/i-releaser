# Data retention: old deployments, logs and jobs

- **Status:** finished (2026-11-24; tested with `tests/test_data_retention.py`, not on IBM i)
- **Type:** feature
- **Priority:** P2
- **Source:** Code review 2026-11-23


## Current situation

Nothing is ever deleted except sessions, login failures and the backups of database updates ([app_sqlite.py](../../modules/db/app_sqlite.py)):

| Data | Grows with |
|---|---|
| Deployments with stages, steps, objects, history (`var/app.sqlite`) | every deployment; a copy of the workflow per deployment (`workflow_definitions`) |
| `action_run_history`, `run_history`, `processing_jobs`, `processing_users` | every run of a step, stage, job, action |
| `meta/{project}/{date}/{version}/` | logs of every step, save files, SQL, compile lists (up to `C_MAX_COMPILE_LIST_SIZE`, 32 MB, each) |
| Application logs `log/`, `webapp/log/` | every request; `FileHandler`/`basicConfig` without rotation ([etc/examples/logger_config.py:41](../../etc/examples/logger_config.py#L41), [webapp/etc/examples/logger_config.py:48](../../webapp/etc/examples/logger_config.py#L48)) |
| WAL file of SQLite | no truncating checkpoint |

On IBM i, a full IFS or a large database makes the web app slow or stop. Lists (deployment list, object history) get slower with each deployment.


## Requirements

1. Setting `C_RETENTION_DAYS` (default 0 = keep everything, as today). Deployments which are `finished` or `canceled` and older than this (time of the last change) are removed:
   * their rows in all tables (with foreign keys, see step 6 of the [core redesign](core-redesign.md), or explicit deletes),
   * their directory in `meta/`.
2. Never removed: the newest finished deployment per project (it shows the current state of production), deployments which are not finished/canceled.
3. Before the removal, a deployment can be archived (`C_RETENTION_ARCHIVE = True`): a JSON file with the deployment (incl. history and step results) and its `meta/` directory as `.tar.gz` in `var/archive/{project}/`.
4. The removal runs once a day in the processing service (or in the web app in mode `thread`), at most `N` deployments per run, and writes a summary to the log and the [audit log](audit-log.md).
5. Settings page: shows the size of the database and of `meta/`, the number of deployments which would be removed, a button "Remove now" (admin).
6. Application logs rotate (`logging.handlers.RotatingFileHandler`, `C_LOG_MAX_MB`, `C_LOG_BACKUPS`), in the examples of `logger_config.py`.
7. After a removal: `PRAGMA wal_checkpoint(TRUNCATE)`; `VACUUM` only on request (it locks the database).
8. The job history (`processing_jobs`) of removed deployments goes with them; finished jobs of other deployments older than `C_RETENTION_DAYS` too.


## Acceptance criteria

- [x] Test: a finished and a canceled deployment older than the limit are removed with their rows and directory; the newest finished one of the project stays; one which isn't finished or canceled stays.
- [x] Test: with archive, the archive file contains the deployment and the directory.
- [x] Test: no orphaned rows after the removal (query over all tables).
- [x] Test: the log rotates at the size limit.


## Non-goals

* Removing single steps' logs of deployments which are kept.
* Restoring an archive into the database (the archive is for reading).


## Decisions (2026-11-24)

* `modules/retention.py`; the web app runs it once a day (hourly check, a lock and `var/retention.last`, so several workers don't run it together). `Settings` → `Data retention` shows the setting, the size of the database, the number of deployments to remove, and a button `Remove now` (admin, recorded in the [audit log](audit-log.md) as `data_removed`).
* The size of `meta/` is not shown: walking a large IFS directory takes too long for a page.
* A directory is only removed if it's below the base directory of `C_META_DIR`.
* Log files: not `RotatingFileHandler`, because several processes write the same file (gunicorn workers, job processes). They are rotated when the web app or the processing service starts (`modules/log_rotation.py`, `C_LOG_MAX_MB`, `C_LOG_BACKUPS`), by the templates of `logger_config.py`. Existing installations add the lines of the template to their `logger_config.py`.
* The finished jobs of deployments which are kept stay (they are few and belong to the deployment page).
* The [notifications](notifications.md) of a removed deployment are removed with it; sent and failed notifications after 30 days (2026-11-24).
* `VACUUM` is not run; after a removal the WAL file is truncated (`PRAGMA wal_checkpoint(TRUNCATE)`).


## Open questions (answered 2026-11-24)

* Default for new installations: keep everything (0) or e.g. 730 days? Proposal: 0, the settings page shows the size.
* Should the version numbers of removed deployments be kept (`deploy_versions`) so a version is never given twice? Proposal: yes, keep `deploy_versions` rows.
