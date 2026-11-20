# Technical notes

<a id="entwicklung"></a>

## Development

### Tests

```bash
.venv/bin/pip install -r requirements-dev.txt   # once
.venv/bin/pytest
```

* Tests are in `tests/` and don't need an IBM i. Tests which do are marked with `@pytest.mark.ibmi` and not run by default.
* Browser tests (`@pytest.mark.browser`, `tests/test_web_browser.py`, `tests/test_web_browser_deployment.py`; fixtures in `tests/conftest.py`) open the web app in Chromium with Playwright. They run with every `pytest` where Playwright and its browser are installed (`.venv/bin/python -m playwright install chromium`, once, about 150 MB outside the repository) and are skipped otherwise, e.g. on IBM i. Only them: `.venv/bin/pytest -m browser`.
  A browser test fails on a script error, an error in the console, a failed request and a request to another server (`Page_Watch` in `tests/browser_tools.py`).
* The screenshots of `README.md` are made from test data: `.venv/bin/python tests/screenshots.py` writes `docs/img/*.png` (`--out <dir>` to compare first). It runs the web app with own workflows, deployments and the [rollback example](scripts.md#scripts-of-custom-templates), and replaces the directory of the test copy. A browser test checks that it makes every picture of `README.md`.
* `tests/web_server.py` runs the real web app for a test: a copy of the repository in a temporary directory, with its own configuration and database.
  `Client` behaves like a browser (session cookie, `Origin` header).
* Other tests use a temporary database, see `setUp` in `tests/test_stage_flow.py`.
* Tests never use the real `var/`, `etc/` or `meta/` of an installation.
* `.github/workflows/tests.yml` runs the tests and `pip-audit` for every push and pull request.

Security check of the dependencies: `.venv/bin/pip-audit -r requirements.txt`. It reports 5 advisories of `starlette` which don't apply, see [known vulnerabilities](#known-vulnerabilities).

### Database updates

The database stores its schema version in `PRAGMA user_version`, independent of the application version and the configuration.

To add an update: add a function to `modules/db/updates/`, add it to `app_sqlite.get_updates()` and raise `SCHEMA_VERSION`.
For a new column, also add it to `create_tables`: a new database starts with the current version and runs no updates.

`check_updates` runs at the start of the web app, under a lock (gunicorn starts several workers). It makes a backup first and restores it if an update fails.
The processing service only checks the version.

No Alembic: it would be a new package, for a handful of small updates.

### Version

The application version is in the file `VERSION`. It has to match the first line of `CHANGELOG.md` (there is a test).


## Decisions

### User of a request

`modules/current_user.py` keeps the user in a `ContextVar`, so concurrent requests can't see each other's user. A thread doesn't inherit the context: `run_current_stage_as_thread` uses `contextvars.copy_context().run`.

### Saving a deployment

Each run of a stage has its own copy of the deployment. To keep copies from overwriting each other:

* Objects remember the values they were loaded with (`saved_values`), and `app_sqlite.update_changes` only writes changed columns.
* Shared data is changed in the database, not in the copy: `stage_data.claim_stage` (a stage can only be started once), `stage_data.activate_stage` (only `new` → `ready`), `meta_file_data.claim_finished`, `meta_file_data.change_custom_data`.
* `Meta_File.refresh_state` takes over status of deployment and stages from the database, before decisions are made. It overwrites these values in memory, so save first.
* The status of a deployment after a run follows from its stages (`set_status_after_stage_run`).
* The status of deploy objects: the last write wins per object.

### Parallel steps

`modules/parallel_steps.py` runs the steps of a group in a `ThreadPoolExecutor` (standard library, no new package). The commands are processes, the threads only wait for them.

* The running group is a `ContextVar` and not an attribute of `IBM_i_commands`: scripts create an instance per function. Each run of a stage and each `SCRIPT` step has its own scope, so sub-steps can't end the group of the stage.
* A step doesn't set its stage to `failed`: a failed stage can be run again, also while other steps of the group are still running. `_run_current_stage` sets it after the run has ended.
* All parallel steps share one `Meta_File`, so `save` takes a lock. Usually the first update of a save locks the database anyway, but not if nothing has changed for this save: two saves at the same time could add the same new sub-step twice.
* The history log of a deployment is bound to the context instead of the thread, so it contains the log entries of the parallel steps.

### Errors

`modules/errors.py` contains the errors which are meant for the caller, with their HTTP status. `WebMiddleware.get_error_response` creates all error responses, so route handlers don't catch exceptions.
Other exceptions are unexpected: the caller gets a general message with an id, the details are in the log.

### Web requests

Route handlers are plain functions (FastAPI runs them in threads), so blocking work doesn't stop other requests. Handlers have to be thread safe.

### CSRF

For requests with a session cookie, `WebMiddleware.check_session_request` requires `POST` for actions and an `Origin` or `Referer` of the own host. API tokens aren't sent automatically by browsers, so requests with a token don't need this.
No CSRF token: the header check needs no changes in the pages, and all current browsers send `Origin` with `POST`.

### Content-Security-Policy

Every HTML page is sent with

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self';
    connect-src 'self'; media-src 'none'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

and every response with `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `X-Frame-Options: DENY` (`webmiddleware.CacheControlMiddleware`).

* The browser runs only script files of the web app: no inline scripts, no `on...=` attributes, no `eval`. A value which gets into a page as HTML can't run as a script. The [rules](features/web-ui-scripts.md#rules) for templates and scripts are checked by `tests/test_web_scripts.py`, without exceptions.
* `style-src 'unsafe-inline'`: SweetAlert2 and bootstrap-table set `style` attributes. Styles can't run code.
* `/docs` starts Swagger UI with a script file (`swagger-init.js`), not with the inline script of FastAPI: no nonce is needed.
* `C_CSP_REPORT_ONLY = True` in `etc/settings.py` sends the policy as `Content-Security-Policy-Report-Only`: violations are reported in the console of the browser, not blocked. For the time an installation moves its custom templates.
* `Strict-Transport-Security` is set by the [reverse proxy](installation.md#reverse-proxy).
* The browser tests run with the policy: a violation is an error in the console and fails the test. Playwright's `wait_for_function` uses `eval` and is blocked; the tests use `browser_tools.wait_until`.

### Files of the web pages

No page loads anything from another server (`tests/test_web_pages.py`). Libraries are files in `webapp/static/assets/`.
`/docs` is an own route with the local Swagger UI, `/redoc` is turned off (`initial.py`).
To update Swagger UI: `npm pack swagger-ui-dist@<version>`, copy `swagger-ui-bundle.js`, `swagger-ui.css` and the licenses, remove the `sourceMappingURL` lines.

### Values in web pages

Values are never written into inline JavaScript (`onclick="f('{{ value }}')"`): the browser decodes `&#39;` before it runs the handler.
Handlers read `data-*` attributes; scripts build HTML with the DOM (`textContent`), `escape_html` (`app/dom.js`) only where a library needs HTML text (bootstrap-table formatters). Python uses `html.escape`. No `|safe` for data.

### Deployment page

`web_modules/deployment_view.py` prepares all data of the page: actions with their permission (disabled with the reason), the attention bar, the selected stage, the steps of a stage grouped (parallel groups, folded runs of finished steps). `web_modules/stage_flow.py` computes the layout of the flow (columns, rows, connections as SVG paths). The templates (`overview/deployment/macros.html`) decide nothing.
The steps of a stage are a part of the page (`GET /show_details/{id}/stage/{stage_id}`), loaded by `pages/deployment.js` when a stage is selected and when its state changes (auto refresh).

### Scripts of the web pages

Scripts are files: ES modules in `webapp/static/assets/js/` (`app/` the helpers, `pages/` one file per page), without a build step. Templates contain only `<script src>` and data blocks (`<script type="application/json">`), no `on...=` attributes ([rules](features/web-ui-scripts.md#rules)).
`tests/test_web_scripts.py` checks the rules; templates which are not moved yet are listed in `LEGACY_TEMPLATES` and moved with their step of the [modernization](features/web-ui-modernization.md).
`app/api.js` is the one `fetch` of the pages: errors of the server become exceptions with the server's message, `401` shows `Your session has ended`. It sends `X-Requested-With: fetch`, so the web app answers errors as JSON also for parts of pages (`WebMiddleware.wants_html`). `app/theme.js` is the only script in `<head>`: it sets the theme before the page is drawn.

### Placeholders

`modules/placeholders.py` replaces only known placeholders. `PASE` values are quoted depending on the position in the command (outside of quotes, in `'...'`, in `"..."`). `QSYS` values from users are checked instead of quoted, as they can be inside or outside of a CL string.

### Request path

The middleware decides on `request.scope['path']` (`get_path`), the path the router uses. `request.url` is built with the `Host` header, which the client chooses.

### FastAPI and pydantic

`pydantic` 2 doesn't install on IBM i: `pydantic-core` needs Rust (checked 2026-11-04).
So `fastapi` stays at 0.125.0, the newest version with `pydantic` 1, and with it `starlette` at 0.50.0.
If this line gets new advisories, the way out is plain Starlette 1.x without FastAPI (the app uses no `pydantic` models or `Depends`).

### Known vulnerabilities

`pip-audit` reports these advisories of `starlette` 0.50.0. The CI ignores them (`.github/workflows/tests.yml`):

| Advisory | Why ignored |
|---|---|
| PYSEC-2026-161: `request.url` built with the `Host` header | The middleware uses the router path, see [request path](#request-path) |
| PYSEC-2026-248: `request.url.hostname` can be changed by the path | Not used |
| PYSEC-2026-249: no limits for urlencoded forms | The only form, the login, is limited to 4 KB before it's read (`LOGIN_FORM_MAX_BYTES` in `webmiddleware.py`) |
| PYSEC-2026-2280: `HTTPEndpoint` calls any method | Not used |
| PYSEC-2026-2281: `StaticFiles` SSRF | Windows only |

Before using one of these features (or a new form), upgrade or check again.


<a id="package-prüfung"></a>

## Package review

Criteria: see [architektur.md](architektur.md). Checked on 2026-11-01.

| Package | Used for | Stars | Forks | Result |
|---|---|---|---|---|
| `pytest` | Tests (`requirements-dev.txt`) | 14659 | 3583 | OK |
| `pip-audit` | Check of the dependencies (`requirements-dev.txt`) | 1389 | 149 | OK |
| `playwright` 1.65.2 (`microsoft/playwright-python`, Apache-2.0, checked 2026-11-19) | Browser tests (`requirements-dev.txt`) | 15115 | 1258 | OK |
| `swagger-ui-dist` 5.35.0 (JavaScript, `webapp/static/assets/swagger-ui/`, checked 2026-11-17) | `/docs`, instead of the copy FastAPI loads from a CDN | 29085 | 9245 | OK |

Removed: `starsessions` and `aiofiles` (not used anymore).

### Libraries of the web pages

Files in `webapp/static/assets/`, checked on 2026-11-17. Each library exists once, as minified file; the licenses are in `assets/licenses/`.

| Library | Version | Used for | Repository | Stars | Forks | License | Result |
|---|---|---|---|---|---|---|---|
| Bootstrap | 5.3.9 | Layout and components (`bootstrap.min.css`, `bootstrap.bundle.min.js` with Popper) | `twbs/bootstrap` | 175072 | 79484 | MIT | OK |
| Bootstrap Icons | 1.13.2 | Icons (the only icon set) | `twbs/icons` | 8184 | 1122 | MIT | OK |
| bootstrap-table | 1.28.0 | Tables with sorting, filters and paging (with the filter-control extension) | `wenzhixin/bootstrap-table` | 11812 | 4330 | MIT | OK |
| jQuery | 3.7.1 | Needed by bootstrap-table | `jquery/jquery` | 59898 | 20685 | MIT | OK |
| SweetAlert2 | 11.26.25 | Dialogs | `sweetalert2/sweetalert2` | 18103 | 1615 | MIT | OK, see note |
| Prism | 1.30.0 | Highlighting of commands and JSON (languages clike, javascript, bash, json, sql) | `PrismJS/prism` | 13070 | 1411 | MIT | OK |
| Swagger UI | 5.35.0 | `/docs` | `swagger-api/swagger-ui` | 29085 | 9245 | Apache-2.0 | OK |

Note on SweetAlert2: versions from 11.4.9 on (also 11.7.20, used until 2026-11) contained code which blocked the page and played audio from another server for browsers with a Russian language setting on `.ru`, `.su`, `.by` and `.рф` hosts. 11.26.25 doesn't contain it. Check `sweetalert2.min.js` for `navigator.language` at each update.

To update a library: `npm pack <package>@<version>` in an empty directory, copy the minified files named above (and the license) over the old ones, remove `sourceMappingURL` lines, update this table, run the tests and open each page.
Prism: download from prismjs.com with the languages of its first line.

The other packages of `requirements.txt` have not been reviewed yet. `starlette` is pinned now (it was only a dependency of `fastapi`), see [FastAPI and pydantic](#fastapi-and-pydantic).
