# Back up the database before updates

- **Status:** finished
- **Type:** feature
- **Priority:** P2


## Current situation

`docs/architektur.md` requires a backup of the database before every update.
Today the web app updates the database at its start without a backup ([app_sqlite.py:272](../../modules/db/app_sqlite.py#L272)).
A failed update can leave a partly updated database (see [database updates](../bugfixes/db-migrations-rerun-on-every-start.md)).


## Requirements

1. Before the first database update step runs, the database is copied with the SQLite backup function (consistent, also in WAL mode), e.g. to `var/backup/app-<schema version>-<timestamp>.sqlite`.
2. If the backup fails, no update runs and the start stops with a clear message.
3. No backup if there's nothing to update.
4. The last N backups are kept (setting, e.g. 5).
5. `docs/installation.md` describes how to restore a backup.


## Acceptance criteria

- [x] Test: start with an update → a backup with the old schema version exists, and it can be opened.
- [x] Test: start without an update → no new backup.
- [x] Test: backup directory not writable → no update, start stops with a message.
- [x] Test: only the configured number of backups is kept.


## Non-goals

* Backup of `meta/` and the configuration


## Decisions

* How many backups? **5**
