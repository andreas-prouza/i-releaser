# Session handling: unchecked session id, cookie flags, cleanup

- **Status:** finished
- **Type:** security
- **Priority:** P1
- **Found:** 2026-10-23, code review; cookie flags reproduced
- **Confidential:** don't publish before the fix is released


## Current situation

* The session id from the cookie is used as file name without a check ([server_sessions.py:19](../../webapp/web_modules/server_sessions.py#L19)): `sessions/{id}.json`.
  A cookie like `../../etc/x` reads (and, if the file looks like an expired session, deletes) JSON files outside `webapp/sessions/`.
* The cookie is `HttpOnly; SameSite=lax`, but without `Secure`: behind HTTPS it's also sent over plain HTTP.
* Expired session files are only deleted when the same id is used again. `webapp/sessions/` grows forever.
* A second, unused session system is configured: `starsessions.SessionMiddleware` with `FileSystemStore` ([initial.py:39](../../webapp/routes/initial.py#L39), [webmiddleware.py:21](../../webapp/routes/webmiddleware.py#L21)), with the same cookie name `session_id`. The comment `cookie_https_only=False   # Prevents JS from accessing the cookie` is wrong.
* A session lasts as long as it's used: there's no maximum lifetime.


## Requirements

1. The session id from the cookie has to be a UUID. Otherwise it's treated as "no session"; no file is read or deleted.
2. Cookie flags: `HttpOnly`, `SameSite=Lax` (explicit), `Secure` when the web app is used over HTTPS (setting, or derived from the reverse proxy).
3. Expired session files are deleted at the start of the web app and regularly (e.g. hourly).
4. Remove the starsessions middleware, `FileSystemStore` and, if unused, the package from `requirements.txt`.
5. Maximum lifetime of a session (e.g. 12 hours) in addition to the idle time of one hour.
6. Remove the cleanup advice from `docs/installation.md` when done.


## Acceptance criteria

- [x] Unit test: cookie `../../etc/x` or `abc` → new session, no file access outside `webapp/sessions/`.
- [x] Unit test: expired session files are deleted by the cleanup, current ones are kept.
- [x] Test: with HTTPS enabled the cookie has `Secure`.
- [x] Test: a session older than the maximum lifetime isn't accepted, even if it was used a minute ago.
- [x] `starsessions` isn't imported anymore.


## Non-goals

* Sessions in the database instead of files


## Decisions

* How to know about HTTPS? **Setting `C_COOKIE_SECURE` in `webapp/etc/global_cfg.py`, added to the production checklist.**
* Maximum lifetime? **12 hours.**
