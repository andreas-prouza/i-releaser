# Nobody can unblock a login if all admins are blocked

- **Status:** finished (2026-11-24; tested with `tests/test_login.py`, not on IBM i)
- **Type:** bug (operation)
- **Priority:** P3
- **Found:** 2026-11-24, code review (while helping an installation after the update to 4.1.0)


## Current situation

Since 4.1.0 a user is blocked after `C_LOGIN_MAX_FAILURES` (2) wrong passwords in a row, without time limit ([login-can-disable-ibm-i-profiles](login-can-disable-ibm-i-profiles.md)).
Only an admin unblocks it in the web app. If the only admin (or all admins) is blocked, the only way was an SQL statement in `installation.md`,
which needs the `sqlite3` command (not always installed on IBM i) and isn't recorded in the audit log.


## Requirements

1. Command line in the directory of i-Releaser:
   * `.venv/bin/python -m modules.db.login_failure_data` lists the blocked users with the number and time of the failures.
   * `.venv/bin/python -m modules.db.login_failure_data unblock <user>` unblocks the user (any case) and its wrong codes of the two-factor authentication.
2. The unblock is recorded in the [audit log](../features/audit-log.md): event `login_unblocked`, without user of i-Releaser, details `source: command line` and the OS user.
3. `installation.md`: production checklist and troubleshooting.


## Acceptance criteria

- [x] Test: list, unblock (upper case name), unblock of a user without failures, wrong arguments (exit code 2), audit entry, login works afterwards.


## Decisions (2026-11-24)

* In the module of the data (`login_failure_data`), like `python -m modules.db.app_sqlite`: no new directory for one command.
* Whoever can run it can also change the database: the command doesn't ask for a permission.
