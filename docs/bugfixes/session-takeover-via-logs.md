# Session takeover through the logs

- **Status:** finished
- **Type:** security
- **Priority:** P0
- **Found:** 2026-10-23, reproduced on a copy of the web app
- **Confidential:** don't publish before the fix is released


## Current situation

Three problems together let any logged-in user take over the session of another user:

1. **Session ids in the log.** The web app logs at `DEBUG` by default (`webapp/etc/examples/logger_config.py`).
   For requests without a login, the middleware logs the whole session object, including its id ([webmiddleware.py:146](../../webapp/routes/webmiddleware.py#L146)).
2. **The session id isn't renewed at the login.** An empty session is replaced on the next request (only by accident: an empty dict is falsy in `SessionManager.load`).
   But after a failed login the session contains `error_text`, so it's kept and becomes the session of the successful login.
3. **Every logged-in user can read the logs** (menu `Logs`, `/log/{log}`, [routes.py:129](../../webapp/routes/routes.py#L129), no permission check).

Reproduction:

1. `boss` (admin) mistypes the user name once, then logs in correctly.
2. `intern` (read only) opens `/log/index/100000` and finds the session id of the failed login.
3. `intern` sends it as cookie `session_id` and gets `/settings` as `BOSS`.

In addition, the logout keeps the session file and only marks it as invalid.


## Requirements

1. Every successful login creates a new session id. The old session file is deleted.
2. The logout deletes the session file and the cookie.
3. Session ids, cookies, passwords and API tokens are never written to a log, at any log level. Session objects are never logged.
4. Only users with the permission `admin` can see the menu `Logs` and open `/log/...`. The log name is checked against the files of the log directory.
5. The templates `webapp/etc/examples/logger_config.py` and `etc/examples/logger_config.py` use `INFO`.
6. Changelog: advise to delete old debug logs after the update.


## Acceptance criteria

- [x] Test: failed login, then successful login → the session id after the login differs from all ids the client had before.
- [x] Test: after a login (failed and successful), the web app log contains none of the issued session ids, with log level `DEBUG`.
- [x] Test: a user without `admin` gets 403 for `/log/...`, and the menu `Logs` isn't shown.
- [x] Test: after the logout, the old session id isn't accepted anymore.


## Non-goals

* Log rotation
