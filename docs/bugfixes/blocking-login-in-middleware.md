# The login blocks all requests of a worker

- **Status:** ready (implemented 2026-11-23, tested with `tests/test_login.py`. Open: check on an IBM i that the IBM i Access ODBC driver ends the sign-on after the login timeout)
- **Type:** security / performance
- **Priority:** P1
- **Found:** 2026-11-23, code review
- **Confidential:** don't publish before the fix is released


## Current situation

The login is done by the middleware, in `async dispatch` ([webmiddleware.py:265](../../webapp/routes/webmiddleware.py#L265)):
`app_login.connect` calls `pyodbc.connect` ([app_login.py:75](../../webapp/web_modules/app_login.py#L75)) directly on the event loop, without a timeout.

* While the IBM i checks the password (or doesn't answer, e.g. network problem, host server down), **every** request of this worker waits: pages, API calls and the live updates (SSE) of all users.
* A few logins at the same time (or an attacker sending logins) can stop the web app. Without a timeout this can last minutes.
* The same is true, in a smaller way, for the other blocking work in the middleware: SQLite for the login failures, the session files, the file lock of `keys.json` ([app_login.py:139](../../webapp/web_modules/app_login.py#L139)).

[No blocking work in async handlers](../features/performance-blocking-handlers.md) fixed this for the route handlers, not for the middleware.


## Requirements

1. The ODBC connect of the login runs in a thread (`starlette.concurrency.run_in_threadpool`), not on the event loop.
2. The connect has a timeout: `C_LOGIN_TIMEOUT_SECONDS` (default 15). Use the login timeout of pyodbc (`pyodbc.connect(..., timeout=...)`); if the IBM i Access ODBC driver doesn't support it, the thread is abandoned after the timeout and the login fails.
3. The number of logins at the same time per worker is limited (e.g. a semaphore of 4). More logins get `503` with "Too many logins at the same time, try again".
4. The other blocking calls of the middleware (session files, login failures, `keys.json`) also run in a thread.
5. A timeout counts as failed login for the lockout of the client, but not for the user (it isn't a wrong password).


## Acceptance criteria

- [x] Test: while a login hangs (simulated connect which sleeps), another request of the same worker is answered within 1 second.
- [x] Test: a hanging login ends after the timeout with the normal error message.
- [x] Test: a login above `C_LOGIN_MAX_PARALLEL` gets `503`.


## Non-goals

* Moving the login into a route handler. That is part of the [login rework of the 2FA](../features/two-factor-authentication.md), which uses this fix.


## Decisions (2026-11-23)

* Own `ThreadPoolExecutor` (standard library) for the sign-ons, size `C_LOGIN_MAX_PARALLEL`, instead of the thread pool of Starlette: independent of the version of `anyio` on IBM i.
* If the driver doesn't end a sign-on, the request gives up after the timeout + 2 seconds; the thread ends when the driver returns.
* A timeout of the driver (SQLSTATE `HYT00`/`HYT01`) or of the request counts as failed login of the client, not of the user.

## Open questions

* Does the IBM i Access ODBC driver in PASE support the login timeout of pyodbc (`SQL_ATTR_LOGIN_TIMEOUT`)? To be checked on an IBM i.
