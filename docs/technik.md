# Technical notes

<a id="entwicklung"></a>

## Development

### Tests

```bash
.venv/bin/pip install -r requirements-dev.txt   # once
.venv/bin/pytest
```

* Tests are in `tests/` and don't need an IBM i. Tests which do are marked with `@pytest.mark.ibmi` and not run by default.
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

Removed: `starsessions` and `aiofiles` (not used anymore).

The other packages of `requirements.txt` have not been reviewed yet. `starlette` is pinned now (it was only a dependency of `fastapi`), see [FastAPI and pydantic](#fastapi-and-pydantic).
