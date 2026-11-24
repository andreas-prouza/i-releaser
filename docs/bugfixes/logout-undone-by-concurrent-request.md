# A logout can be undone by a request which runs at the same time

- **Status:** finished (2026-11-23; tested with `tests/test_review_2026_11.py`, `tests/test_web_security.py`)
- **Type:** security
- **Priority:** P1
- **Found:** 2026-11-23, code review
- **Confidential:** don't publish before the fix is released


## Current situation

* `SessionManager.pop` always marks the session as changed ([server_sessions.py:190](../../webapp/web_modules/server_sessions.py#L190)).
  The middleware calls `pop('error_text')` for every request ([webmiddleware.py:228](../../webapp/routes/webmiddleware.py#L228)),
  so **every** request writes its session file and sets the cookie again at its end ([webmiddleware.py:93](../../webapp/routes/webmiddleware.py#L93)).
* `/logout` deletes the session file (`destroy`, [server_sessions.py:155](../../webapp/web_modules/server_sessions.py#L155)).
* A request of the same session which was loaded before the logout and ends after it writes the session back with `is_logged_in`
  (`save` → `save_session` creates the file again, [server_sessions.py:73](../../webapp/web_modules/server_sessions.py#L73)).
  The deployment page sends requests all the time (live updates), so this is likely, not theoretical.
* Someone with a stolen session id can keep the session alive after the victim has logged out by sending requests in a loop. Only the absolute limit of 12 hours ends it.
* A failed or blocked login stores `error_text` in a new session ([app_login.py:63](../../webapp/web_modules/app_login.py#L63), [app_login.py:93](../../webapp/web_modules/app_login.py#L93)).
  Each such request creates a session file, which is removed only by the hourly cleanup: requests without a login can fill the disk (files and inodes).
* Every request also resets the idle timeout, including the automatic ones of an open page. An unattended open browser tab never times out (only the 12 hours).


## Requirements

1. A session is only written if its content has changed (`pop` of a missing key is no change).
2. A session which doesn't exist anymore is never created again by `save`. Only a new session (login) or `regenerate` creates a file.
   Proposal: `save` writes with "replace only if the file exists", a new session with "create only if it doesn't exist".
3. A failed login doesn't create a session file: the error text is given to the login page directly (e.g. as part of the response), not through the session.
4. Automatic requests of a page (live updates, `X-Requested-With: fetch` without user action) don't extend the idle timeout. Proposal: the page sends `X-Background: 1`, the middleware doesn't touch `last-update` for these.
5. `/logout` only with `POST` (see [minor web defects](minor-web-defects-2026-11.md)).


## Acceptance criteria

- [x] Test: a request which started before `/logout` and ends after it doesn't make the session valid again (the next request gets 401 / the login page).
- [x] Test: failed logins create no session file (9, below the block of the client address).
- [x] Test: a request which only reads doesn't change the session file (modification time).
- [x] Test: requests with `X-Background: 1` don't extend the session, other requests do.


## Non-goals

* A different session store (e.g. in SQLite). Could be done with the [core redesign](../features/core-redesign.md).


## Decisions (2026-11-23)

* Idle timeout stays 1 hour, also for pages left open (proposal accepted).
* The cookie has no `Max-Age` anymore (it was refreshed with every request before): the browser forgets it when it's closed, the server enforces the timeouts.
* A session is extended at most once a minute (`TOUCH_INTERVAL`), so reading pages doesn't write files.

## Open questions

* None.
