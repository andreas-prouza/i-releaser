# 3.1.0

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
* [Reset the last finished stage](docs/workflow.md#reset-the-last-finished-stage)
* [DB deployment](docs/db-deployment.md): deploy changes of large tables with minimal downtime
* [Documentation](README.md#documentation) restructured
* Security hardening: sessions, API tokens, CSRF, CORS, permission checks, login limit (see [production checklist](docs/installation.md#production-checklist))
* Parallel stages don't overwrite each other, a stage can only be started once, stages without steps finish automatically (see [concepts](docs/concepts.md#running-a-stage))
* Steps: `fail_on_stderr`, `timeout_seconds`, correct exit code of `QSYS` steps, object commands are run (see [step actions](docs/workflow.md#step-actions))
* [Parallel steps](docs/workflow.md#parallel-steps)
* Workflows: [`create_fields`](docs/workflow.md#create-fields), one invalid workflow file doesn't stop the others
* [Backup of the database before updates](docs/installation.md#backups-before-updates)
* Web API: [consistent status codes and errors](docs/webapi.md#responses-and-errors)
* Local settings in `etc/settings.py` (see [configuration files](docs/installation.md#configuration-files))
* Web app: requests don't block each other
* [Tests](docs/technik.md#tests) in `tests/`, run on GitHub
* Removed: `deployment.py`, `stage_commands.json`, `flask_config.py`, `gen_commands.py`

## Before you update to 3.1.0

* Move your changes of `etc/constants.py` to `etc/settings.py`, then `git checkout etc/constants.py` and `git pull`
* Scripts: remove workarounds for `$` (e.g. `replace('$', '\\$')`), [commands](docs/workflow.md#commands) reach `cl` unchanged now
* Own clients: `POST`, `Authorization: Bearer` and the new [error format](docs/webapi.md#responses-and-errors)
* Generate new [API tokens](docs/permissions.md#api-tokens)
* Check the [production checklist](docs/installation.md#production-checklist) (log level, `C_COOKIE_SECURE`) and the [reverse proxy](docs/installation.md#reverse-proxy) (`ProxyPreserveHost On`)
* Start the web app first, it updates the database (see [update](docs/installation.md#update))
