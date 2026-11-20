# 4.0.0

* Store source file name in deploy-objects
* Add support to run sql scripts as deployment
* Add properties for deploy-objects
* Styles
* Bugfixes
* Store logs in meta_file dir to shrink db size
* Option to automatically run next stage
* Define editable fields in custom-data
* Auto refresh of the deployment page and the stage steps window
* Finish permission maintenance
* Workflow hooks: run scripts when a deployment or stage changes its status
* Jira integration: show deployments in Jira (Cloud: development panel, Data Center: issue links)
* Faster processing steps: no more piling up log handlers, less logging and fewer DB queries per step, DB indexes
* Log the duration (prepare, execute, save) of each processing step
* Database uses WAL mode: back up `var/app.sqlite-wal` and `var/app.sqlite-shm` together with `var/app.sqlite`
* Deployment history logs are stored again
* [Processing service](docs/processing-service.md): stages keep running if the web server ends
* Processing mode and processing service in the web app (see [processing service](docs/processing-service.md#set-up))
* [Start the processing service automatically](docs/processing-service.md#start-automatically) with the web app, and again after a crash. Only one service can run at the same time. `etc/web_settings.json` is renamed to `etc/app.json`
* [Reset the last finished stage](docs/workflow.md#reset-the-last-finished-stage)
* [DB deployment](docs/db-deployment.md): deploy changes of large tables with minimal downtime
* [Documentation](README.md#documentation) restructured
* Security hardening: sessions, API tokens, CSRF, CORS, permission checks, login limit (see [production checklist](docs/installation.md#production-checklist))
* Parallel stages don't overwrite each other, a stage can only be started once, stages without steps finish automatically (see [concepts](docs/concepts.md#running-a-stage))
* Steps: `fail_on_stderr`, `timeout_seconds`, correct exit code of `QSYS` steps, object commands are run (see [step actions](docs/workflow.md#step-actions))
* [Parallel steps](docs/workflow.md#parallel-steps)
* Workflows: [`create_fields`](docs/workflow.md#create-fields), one invalid workflow file doesn't stop the others
* [Compile list](docs/webapi.md#create-a-deployment): `compiles` of the OBI build list is stored beside the custom data, so large builds aren't rejected by its 64 KB limit. Scripts read it with [`meta_file.get_compile_list()`](docs/scripts.md#compile-list)
* [Backup of the database before updates](docs/installation.md#backups-before-updates)
* Web API: [consistent status codes and errors](docs/webapi.md#responses-and-errors)
* Local settings in `etc/settings.py` (see [configuration files](docs/installation.md#configuration-files))
* Web app: requests don't block each other
* [Tests](docs/technik.md#tests) in `tests/`, run on GitHub; browser tests with Playwright (development only)
* FastAPI 0.125, `starlette` 0.50 (see [FastAPI and pydantic](docs/technik.md#fastapi-and-pydantic))
* Web pages load no files from other servers any more; `/docs` uses a local Swagger UI, `/redoc` is turned off
* Web pages: names of objects, stages, users and commands with special characters (`'`, `<`, `->`, spaces, `.`, `#`) are shown as text and don't break pages. The permissions page saves them correctly
* Deployment page, objects: one row per object (the level is a column), `All ready` / `None ready` for the objects which match the filters in one request ([`set_objects_ready`](docs/webapi.md#steps-and-objects)), switches which can't be used are disabled, no sideways scrolling
* `/api/save_permissions` keeps users and roles which are not sent; delete with `deleted_users` / `deleted_roles` (see [Web API](docs/webapi.md#users-and-permissions))
* Static files of the web app cleaned up (35 MB → 3 MB): Font Awesome, unused fonts, stylesheets and scripts removed; Bootstrap 5.3.9, bootstrap-table 1.28, SweetAlert2 11.26 (see [libraries](docs/technik.md#libraries-of-the-web-pages))
* New layout of the web app (see [layout](docs/features/web-ui-layout.md)): navigation which can be collapsed to its icons, dark mode (follows the browser, switch in the navigation), page headers with breadcrumb and status, new login and error page. `Configuration` is now `Settings`, `Object list` is `Objects`; the projects are only above the deployment list. Settings and logs are only in the navigation of administrators. After the login the page opens which was asked for
* New deployment page (see [deployment page](docs/features/web-ui-deployment-page.md)): a bar which says what the deployment waits for, the stages as flow with parallel branches, the steps of the selected stage on the page (closed, opened by itself at the latest error; filter, groups of parallel steps), logs in one dialog with Output and Errors, activity with actions and run logs. Buttons without permission are disabled with the reason
* Deployment page: [live updates](docs/features/web-ui-live-updates.md) without loading the page again (filters, open steps and dialogs stay); after a lost connection it connects again and shows `Reconnecting …`. `watch_state` has `parts`
* [Lists](docs/features/web-ui-lists.md): projects as tabs with their open deployments, `/project/{project}` can be shared, a column `Stage`, a click on a row opens the deployment. The object list finds every object (page by page from [`/api/deploy_objects`](docs/webapi.md#steps-and-objects)), not only the newest 1,000. `Start workflow` with the fields of [`create_fields`](docs/workflow.md#create-fields)
* [Permissions page](docs/features/web-ui-permissions-page.md) of its own: a table per user and role, permissions from roles and higher levels shown, roles with permissions for workflows and stages, description and mail. A change of another session isn't overwritten (`version`, `409`), the last administrator can't be removed
* [Admin pages](docs/features/web-ui-admin-pages.md): settings as `General` and `Processing` (updated without loading the page, jobs with stage and duration), logs with filter by level and text and download, workflows with their stages as flow, `My account` with roles and permissions
* [Content-Security-Policy](docs/technik.md#content-security-policy) and security headers: the browser runs only script files of the web app
* Scripts of the web pages are files; helpers for custom templates: `app/api.js`, `app/dialogs.js`, `app/dom.js` (see [scripts of custom templates](docs/scripts.md#scripts-of-custom-templates)). An ended session is shown as such. Starting a workflow on the workflows page asks once
* A step is `in process` while it runs (the Web API showed it `new` until it had ended), also each step of a group of [parallel steps](docs/workflow.md#parallel-steps)
* A stage with `after_stages_finished` stays `new` until those stages are finished (it was `ready`, but couldn't be run). The Web API lists them in `waiting_for` (see [parallel branches](docs/concepts.md#parallel-branches))
* Removed: `deployment.py`, `stage_commands.json`, `flask_config.py`, `gen_commands.py`

## Before you update to 4.0.0

* Move your changes of `etc/constants.py` to `etc/settings.py`, then `git checkout etc/constants.py` and `git pull`
* Scripts: remove workarounds for `$` (e.g. `replace('$', '\\$')`), [commands](docs/workflow.md#commands) reach `cl` unchanged now
* Own clients: `POST`, `Authorization: Bearer` and the new [error format](docs/webapi.md#responses-and-errors)
* Generate new [API tokens](docs/permissions.md#api-tokens)
* Check the [production checklist](docs/installation.md#production-checklist) (log level, `C_COOKIE_SECURE`) and the [reverse proxy](docs/installation.md#reverse-proxy) (`ProxyPreserveHost On`)
* Custom templates: actions need `POST`; a `GET` like `http_getData('/api/start_workflow/...?...')` is rejected with `405`. Put their JavaScript into `webapp/static/custom/` (example and how to move an old template: [scripts of custom templates](docs/scripts.md#scripts-of-custom-templates))
* Custom templates: Font Awesome icons (`fa-...`) are gone, use [Bootstrap Icons](https://icons.getbootstrap.com) (`bi bi-...`). Don't load `sweetalert2.all.min.js` or `popper.min.js` yourself, `base.html` provides `Swal` and Bootstrap
* Own pages of custom routes (templates which extend `base.html`): `content` is not inside a `<form>` any more, `sidebar['projects']` and `sidebar['active']` are gone, set the entry of the navigation with the block `nav_active` (see [own pages](docs/scripts.md#own-pages)). Links don't need `?sidebar_active=` any more
* **Custom templates with inline scripts or `onclick` stop working** (Content-Security-Policy). Move their JavaScript into a file in `webapp/static/custom/`, and use `post_json` / `get_json` of `app/api.js` (or `fetch`) instead of `postData`, `http_post`, `http_get`, `http_getData`, which are removed with `web.deploy.js` (example and table: [scripts of custom templates](docs/scripts.md#scripts-of-custom-templates)). For the transition: `C_CSP_REPORT_ONLY = True` in `etc/settings.py`
* `etc/logger_config.py` and `webapp/etc/logger_config.py`: replace `if not Path.exists(LOG_DIR): os.makedirs(LOG_DIR)` by `os.makedirs(LOG_DIR, exist_ok=True)` (see [log directory](docs/bugfixes/log-dir-race.md))
* Start the web app first, it updates the database (see [update](docs/installation.md#update))
