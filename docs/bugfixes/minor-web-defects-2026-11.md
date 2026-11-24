# Minor defects of the web app and the Web API (review 2026-11)

- **Status:** finished (2026-11-23; tested with `tests/test_review_2026_11.py`, `tests/test_web_security.py`, `tests/test_two_factor.py`, not on IBM i)
- **Type:** security / bug
- **Priority:** P2 (items 1–6) / P3
- **Found:** 2026-11-23, code review
- **Confidential:** don't publish before the fix is released


## Current situation

| # | Defect | Where |
|---|---|---|
| 1 | **Every POST without session is a login attempt.** The middleware takes `user`/`password` of any path; after the login the request continues to its handler. There is no `Origin` check for it (login CSRF: another site can log the browser in as the attacker's user). It also makes a second login step (2FA) impossible. | [webmiddleware.py:253](../../webapp/routes/webmiddleware.py#L253) |
| 2 | **Logout with `GET`.** A link or an image on another site logs the user out. | [index.py:164](../../webapp/index.py#L164) |
| 3 | **The `Origin` check trusts `X-Forwarded-Host`.** Together with CORS (`C_CORS_ALLOWED_ORIGINS`, credentials and all headers allowed) an allowed origin can set the header and pass the check. The scheme isn't compared (only the host). | [webmiddleware.py:184](../../webapp/routes/webmiddleware.py#L184), [initial.py:68](../../webapp/routes/initial.py#L68) |
| 4 | **Pages with data may be cached.** `Cache-Control: max-age=0` allows the browser to store authenticated pages and API answers (e.g. back button after logout, shared PCs). | [webmiddleware.py:61](../../webapp/routes/webmiddleware.py#L61) |
| 5 | **Permission changes of two workers can overwrite each other.** `CHANGE_LOCK` is a `threading.Lock`, but gunicorn runs several processes. The version check and the write aren't atomic between processes (`keys.json` uses the file lock). | [permission_config.py:315](../../modules/permission_config.py#L315), [routes.py:1004](../../webapp/routes/routes.py#L1004) |
| 6 | **Custom routes can replace core routes.** They are loaded before the core routes ([index.py:109](../../webapp/index.py#L109)), and Starlette uses the first matching route, so a custom file can define `/login`. Only `ImportError` is caught: a syntax error stops the web app. | [index.py:117](../../webapp/index.py#L117) |
| 7 | **An example route is part of every installation.** `webapp/custom/routes/test.py` is tracked although `custom/` is meant for own files; every installation has `/custom_test/{test}`, which writes its input to the log. | [test.py](../../webapp/custom/routes/test.py) |
| 8 | **Live updates don't notice a logout.** `/api/watch_state` checks the session only when the stream starts; it keeps sending after logout, session timeout or a removed permission. | [routes.py:894](../../webapp/routes/routes.py#L894) |
| 9 | **Errors of FastAPI itself have another format.** No exception handler is registered: unknown paths (`404`), wrong methods (`405`) and invalid parameters (`422`) answer `{"detail": …}`, also for pages, instead of the error format of [webapi.md](../webapi.md). | [initial.py](../../webapp/routes/initial.py) |
| 10 | **`set_source_ready_4_deployment` doesn't check its input.** A missing key gives `500` (`KeyError` already in the log line), `"checked": "false"` is stored as true. `set_objects_ready` checks the same input correctly. | [routes.py:748](../../webapp/routes/routes.py#L748) |
| 11 | **`C_COOKIE_SECURE` is `False` by default.** Browsers treat `http://localhost` as secure, so `True` also works with the SSH tunnel of the quick start; behind the reverse proxy it must be `True` anyway. | [global_cfg.py:5](../../webapp/etc/examples/global_cfg.py#L5) |
| 12 | **The guard of the local debugging mode** only checks whether gunicorn is loaded. Started with `uvicorn` on a server, the password check is off (with a warning in the log). | [index.py:72](../../webapp/index.py#L72) |


## Requirements

1. Item 1: the credentials are only accepted by `POST /login` (and the `Origin` check applies). The web API uses tokens. The documentation ([webapi.md](../webapi.md)) is changed; the OBI extension uses tokens already (to be checked).
2. Item 2: `/logout` only with `POST` (button in a form). `GET /logout` shows a page with the button.
3. Item 3: the `Origin` is compared with scheme and host of the configured external URL (`C_EXTERNAL_URL`, new setting; default: the `Host` header, without `X-Forwarded-Host`).
4. Item 4: `Cache-Control: no-store` for all answers except `/static/`.
5. Item 5: `CHANGE_LOCK` is replaced by the file lock of `user_permissions.json`, around check and write.
6. Item 6: custom routes are loaded after the core routes. A custom route with the path of a core route stops the start with a clear message. Every exception of a custom file is caught and logged; the web app starts without it (and shows the error on the settings page).
7. Item 7: `test.py` is moved to `docs/examples/` (as example for the documentation) and removed from `webapp/custom/routes/`.
8. Item 8: the stream checks the session (and the permission `read`) at least every 60 seconds and ends if it isn't valid anymore.
9. Item 9: exception handlers for `HTTPException` and `RequestValidationError` give the error format of the web app (JSON for API requests, the error page for pages).
10. Item 10: same check as `set_objects_ready` (or the route is replaced by it, see [API v2](../features/api-v2.md)).
11. Item 11: default `True`; the quick start works unchanged (localhost). `installation.md` explains when `False` is needed (HTTP without TLS on another host, not recommended).
12. Item 12: the local debugging mode also needs `I_RELEASER_LOCAL_DEBUGGING_I_KNOW=yes`, and the web app only listens on `127.0.0.1` with it.


## Acceptance criteria

- [ ] A test for each item. Item 1: a `POST /api/run_stage/...` with `user`/`password` in the form gets `401`.
- [ ] The browser tests pass (login page, logout button).


## Progress

| Item | Status |
|---|---|
| 2 | finished 2026-11-23 (logout button in the navigation, `GET /logout` shows a page with the button), tested with `tests/test_web_security.py` |
| 5 | finished 2026-11-23 (`permission_config.change_lock`: thread lock and file lock) |
| 7 | finished 2026-11-23 (moved to `docs/examples/custom-routes/`) |
| 10 | finished 2026-11-23, tested with `tests/test_review_2026_11.py` |
| 1 | finished 2026-11-23 with the [2FA](../features/two-factor-authentication.md): only `POST /login` accepts credentials, a login form of another origin gets `403`; tested with `tests/test_two_factor.py` |
| 3 | finished 2026-11-23: the `Origin` is compared with the `Host` header, or with `C_EXTERNAL_URL` (scheme and host), not with `X-Forwarded-Host` |
| 4 | finished 2026-11-23: `Cache-Control: no-store` except `/static/` |
| 6 | finished 2026-11-23: custom routes are loaded after the core routes; a path of the web app stops the start with a message; any other error of a file is logged and shown on the settings page, the web app starts without it |
| 8 | finished 2026-11-23: the stream checks session and permission every `C_WATCH_SESSION_CHECK_SECONDS` (60) and ends; the page connects again and gets 401 |
| 9 | finished 2026-11-23: exception handlers for `HTTPException` and `RequestValidationError` |
| 11 | finished 2026-11-23: `C_COOKIE_SECURE = True` in the template and as default |
| 12 | finished 2026-11-23, see decisions |


## Decisions (2026-11-23)

* Item 12: instead of a second environment variable, the local debugging mode refuses to start on IBM i (`platform.system() == 'OS400'`) and with gunicorn. i-Releaser only runs on IBM i in production, so developers don't need anything new.
* Item 3: `C_EXTERNAL_URL` (scheme and host) is a new setting in `etc/settings.py`; without it the `Host` header decides (the reverse proxy keeps it, `ProxyPreserveHost On`).


## Open questions (answered 2026-11-23)

* Item 1: does any user script or IDE integration log in with a form POST to another path than `/login`? (`webapi.md` documents "e.g. to `/`".)
* Item 12: is the extra environment variable acceptable for developers, or should the mode simply refuse to start when not bound to `127.0.0.1`?
