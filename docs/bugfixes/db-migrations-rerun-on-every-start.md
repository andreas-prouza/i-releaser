# Database updates depend on a config value and can make the start fail

- **Status:** finished
- **Type:** bug
- **Priority:** P1
- **Found:** 2026-10-23, reproduced on a copy of the web app


## Current situation

At each start the web app:

1. reads the version of the last row of `app_info`,
2. runs the database updates from that version on (`check_updates`, [app_sqlite.py:272](../../modules/db/app_sqlite.py#L272)),
3. writes `C_APP_VERSION` from `etc/constants.py` as new row into `app_info`.

Problems:

* `C_APP_VERSION` is `2.0.2`, but the updates go up to `2.0.3`. So the 2.0.3 update runs at **every** start. It's idempotent: only warnings.
* The 2.0.1 and 2.0.2 updates are not idempotent. If `C_APP_VERSION` is older than the database (e.g. the template `etc/examples/constants.py` has `2.0.0`, or an old `constants.py` is restored),
  the next start runs them again and the web app **doesn't start anymore**:
  `TypeError: write() argument must be str, not bytes` in `v_2_0_2.extract_logs_2_meta_dir`.
* The version is in a user configuration file, and the changelog says `3.1.0`.
* Updates run without a backup and without a transaction. A failure in the middle leaves a partly updated database.
* The processing service doesn't run the updates. If it starts first after an update, it uses new code with the old database.


## Requirements

1. The database stores its own schema version (e.g. `PRAGMA user_version` or a table `schema_version`), set after each update step. Independent of `C_APP_VERSION` and of `etc/constants.py`.
2. Each update runs once, in order, in a transaction where possible. A failed update stops the start with a clear error and leaves the database at its previous version.
3. Backup of the database before the updates (see [backup before update](../features/db-backup-before-update.md)).
4. The processing service doesn't start if the database is older than the code expects (or runs the updates itself, with a lock).
5. The application version has one source (e.g. a `VERSION` file or `modules/__init__.py`), matches the changelog, and isn't in a user configuration file.
6. Existing installations: the first start sets the schema version from the last `app_info` row once.


## Acceptance criteria

- [x] Test: start twice → the updates run only at the first start.
- [x] Test: a database at the newest version and an old `C_APP_VERSION` in `etc/constants.py` → no update runs, the start works.
- [x] Test: a failing update → the start stops, the database is unchanged, a backup exists.
- [x] Test: the processing service refuses to start with an old database.


## Non-goals

* Changing existing update steps (except making them safe to repeat, if needed)


## Decisions

* `PRAGMA user_version`, a table, or Alembic? **`PRAGMA user_version`. No new package.**
