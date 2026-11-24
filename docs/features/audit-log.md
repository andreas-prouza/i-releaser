# Audit log of security events

- **Status:** finished (2026-11-24; tested with `tests/test_audit_log.py`, `tests/test_web_browser_audit.py`, not on IBM i)
- **Type:** feature (security)
- **Priority:** P2
- **Source:** Code review 2026-11-23


## Current situation

* Each deployment has its history (table `processing_users`, [action_type.py](../../modules/action_type.py)): created, run, scheduled, canceled, reset, custom data, object selection.
* Everything which doesn't belong to a deployment is only in the application log, most of it at `DEBUG` (not written with the recommended level `INFO`):
  * login (successful, failed, blocked), logout,
  * API token created or deleted ([routes.py:335](../../webapp/routes/routes.py#L335)),
  * permissions changed ([routes.py:983](../../webapp/routes/routes.py#L983), [routes.py:1021](../../webapp/routes/routes.py#L1021): `save_permissions` logs nothing),
  * settings changed (processing mode, service, auto start),
  * logs viewed or downloaded.
* An admin can't answer "who gave user X the permission `run` for PROD, and when?" or "who logged in last night?".
* Some history entries are written before the action, also if it fails (see [cancel](../bugfixes/cancel-finished-deployment.md)).


## Requirements

1. New table `audit_log`: time (UTC), user (or `-`), client address, event, object (e.g. user name, setting, deployment id), details (JSON, without secrets), result (`ok`/`failed`).
2. Events: `login`, `login_failed`, `login_blocked`, `login_unblocked`, `logout`, `token_created`, `token_deleted`, `token_revoked`, `2fa_enabled`, `2fa_disabled`, `2fa_reset`, `permissions_changed` (with the difference: added and removed permissions per user/role), `setting_changed` (old and new value), `log_viewed`.
3. Actions on deployments stay in their history; the audit page also shows them (one view over both).
4. Entries are only added; there is no function to change or delete them except the retention (requirement 6).
5. Each entry contains the hash of the previous one (hash chain). A check on the audit page shows whether the chain is complete (detects deleted or changed rows, not a rewrite of the whole table).
6. Retention `C_AUDIT_RETENTION_DAYS` (default 730), cleaned by the [data retention](data-retention.md).
7. Audit page for admins under settings: table (bootstrap-table) with filters for time, user, event; export as CSV.
8. Optional: each entry is also written to a syslog/file in JSON lines (`C_AUDIT_FILE`) for an external SIEM.
9. History entries are written after the action has been successful.


## Acceptance criteria

- [x] A test per event (it's written with user, client and result).
- [x] Test: a permission change records exactly the added and removed permissions.
- [x] Test: changing a row in the database makes the chain check fail.
- [x] Test: no entry contains a password, token or TOTP secret.
- [x] Browser test: audit page with filter and export.


## Non-goals

* Tamper-proof storage (WORM, signature with an external key).
* Logging each read request.


## Decisions (2026-11-24)

* Table `audit_log` in `var/app.sqlite` (`modules/db/audit_data.py`); the web app writes it with `web_modules/audit.py`. An entry which can't be written is logged, it doesn't stop the action.
* `C_AUDIT_FILE` (empty: off) gets each event as JSON line; `C_AUDIT_RETENTION_DAYS` (730) is cleaned once an hour by the web app. After a clean up the chain starts with the oldest remaining entry.
* The page shows the newest 1,000 entries of the audit log and of the histories of the deployments (`Administration` → `Audit`), times in the time zone of the browser, CSV export of the same list.
* Requirement 9 (history entries after the action) was done with [cancel-finished-deployment](../bugfixes/cancel-finished-deployment.md).
* Viewing a deployment is not recorded (proposal accepted); viewing and downloading logs and the CSV export are (`log_viewed`).


## Open questions (answered 2026-11-24)

* Requirement 8: is a file for a SIEM needed? Proposal: yes, it's small; IBM i shops often forward to QAUDJRN-based tools, which could read it.
* Should viewing a deployment be audited? Proposal: no (too many entries).
