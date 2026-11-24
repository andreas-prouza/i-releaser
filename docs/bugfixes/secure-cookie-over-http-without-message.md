# Login over plain HTTP fails without a message

- **Status:** finished (2026-11-24; tested with `tests/test_login.py`, not on IBM i)
- **Type:** bug (regression of 4.1.0)
- **Priority:** P1
- **Found:** 2026-11-24, on an installation after the update to 4.1.0


## Current situation

4.1.0 changed the default of `C_COOKIE_SECURE` from `False` to `True` ([server_sessions.py](../../webapp/web_modules/server_sessions.py), function `set_cookie`).
Installations which don't set it in `webapp/etc/global_cfg.py` get the `Secure` flag on the session cookie after the update.

Browsers store a cookie with `Secure` only for HTTPS and for a secure context over HTTP (`localhost`, `*.localhost`, `127.0.0.0/8`, `[::1]`).
If the web app is reached with plain HTTP from another host (e.g. `http://ibmi:8080`):

1. The login succeeds: the password is right, nothing is written to `login_failures`.
2. The browser drops the session cookie of the answer.
3. The next page has no session: the login page is shown again, **without a message**. Nothing in the log either.

The changelog of 4.1.0 described it as an optional step ("`C_COOKIE_SECURE = True`, unless ..."), not as a changed default.

```mermaid
sequenceDiagram
    participant B as Browser (http://ibmi:8080)
    participant W as Web app
    B->>W: POST /login (user, password)
    W->>W: sign-on on the IBM i: OK
    W-->>B: 303, Set-Cookie: session_id=...; Secure
    Note over B: Secure over plain HTTP: cookie dropped
    B->>W: GET / (no cookie)
    W-->>B: login page, no message
```


## Requirements

1. `POST /login` from a page over plain HTTP to a host which isn't a secure context, with `C_COOKIE_SECURE = True`: the login page shows a message which explains it (HTTPS, or `C_COOKIE_SECURE = False`).
   The page is taken from the `Origin` header (or `Referer`) of the browser, not from the scheme of the request: behind a reverse proxy with HTTPS the web app gets plain HTTP.
2. The check is done before the sign-on on the IBM i: the login can't work anyway, the sign-on would be useless.
3. The web app logs a warning with the address.
4. No session is created for this request.
5. Changelog: the 4.1.0 entry describes the changed default as a breaking change. `installation.md`: troubleshooting entry.


## Acceptance criteria

- [x] Test: login from `http://ireleaser.example` with the default: the page has the message, no cookie, no sign-on, warning in the log.
- [x] Test: plain HTTP to `localhost`, `127.0.0.1` and `*.localhost` logs in.
- [x] Test: with `C_COOKIE_SECURE = False`, plain HTTP to another host logs in.


## Decisions (2026-11-24)

* The message is shown to anyone who sends the form, before the password is checked. It only tells that this address uses plain HTTP, which the visitor knows already.
* No automatic fallback to `Secure = False`: the setting stays a decision of the installation.
