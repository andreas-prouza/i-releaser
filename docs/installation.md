# Installation and operation

* [Requirements](#requirements)
* [Install](#install)
* [Configuration files](#configuration-files)
* [Start and stop](#start-and-stop)
* [Reverse proxy](#reverse-proxy)
* [Production checklist](#production-checklist)
* [Backup](#backup)
* [Update](#update)
* [Logs and troubleshooting](#logs-and-troubleshooting)


## Requirements

On the IBM i where i-Releaser runs:

* Python 3.13 (`python3.13` in the `PATH`)
* IBM i Access ODBC Driver and `pyodbc`. The login checks user and password with an ODBC connection.
  See [this setup](https://github.com/andreas-prouza/python-webapi?tab=readme-ov-file#setup-your-webapi).
* `bash` as `/bin/bash`. `PASE` and `QSYS` commands are run with it.
* `git`, if your steps build from a repository (e.g. `scripts/examples/build.py`)
* `ssh` and `scp` with key authentication to the target systems, if stages run commands remotely (`execute_remote`) or transfer files

The user profile which runs i-Releaser needs the authorities for what your steps do (create libraries, restore objects, ...).
i-Releaser itself needs no special authority.


## Install

```bash
mkdir -p /apps && cd /apps
git clone https://github.com/andreas-prouza/i-releaser
cd i-releaser
./setup3.13.sh
```

`setup3.13.sh`:

1. creates the virtual environment `.venv` (with access to the system packages, e.g. a `pyodbc` installed by yum);
2. installs `requirements.txt`;
3. copies the templates into place, **without overwriting existing files**:
   * `etc/examples/*` → `etc/`
   * `webapp/etc/examples/*` → `webapp/etc/`
   * `scripts/examples/*` → `scripts/`
   * `etc/examples/workflows/*` → `etc/workflows/`, only in a new installation

Then adapt the configuration (see below). At least:

* `etc/user_permissions.json`: replace the sample user `myuser` by your users (see [permissions](permissions.md))
* `etc/workflows/*.json`: your workflows (see [workflow configuration](workflow.md))
* `webapp/etc/global_cfg.py`: `C_DEFAULT_PROJECT`, the project shown after the login. It has to be the `default_project` of one of your workflows.


## Configuration files

Your configuration files are not tracked by git, so updates don't touch them.

| File | Content | Details |
|---|---|---|
| `etc/settings.py` | Your values for the settings of `etc/constants.py`: processing mode, processing service, git branch names, timeouts, `C_CSP_REPORT_ONLY`, ... | [processing service](processing-service.md#settings), [security headers](technik.md#content-security-policy) |
| `etc/app.json` | Settings changed in the web app (`Administration` → `Settings` and `Processing`), they override `etc/settings.py`: processing mode, auto start of the processing service, data retention, timeouts, parallel steps and jobs, git branch names. Written by the web app. Replaces `etc/web_settings.json`. | [processing service](processing-service.md#set-up) |
| `etc/workflows/*.json` | One workflow per file | [workflow configuration](workflow.md) |
| `etc/default_step_action.json` | Commands of the processing steps, for all workflows | [workflow configuration](workflow.md#step-actions) |
| `etc/object_commands.json` | Additional commands for specific objects | [workflow configuration](workflow.md#object-commands) |
| `etc/user_permissions.json` | Users, roles and their permissions. Changes are loaded automatically. | [permissions](permissions.md) |
| `etc/logger_config.py` | Log of the processing service and the command line (`log/`) | |
| `etc/jira.json` | Jira integration (optional) | [Jira](jira.md) |
| `etc/notifications.json` | E-mail, Teams and Slack messages for events of the deployments (optional, template in `etc/examples/`) | [notifications](features/notifications.md) |
| `etc/db_deployment.json` | Database connections of the DB deployment (optional) | [DB deployment](db-deployment.md) |
| `webapp/etc/gunicorn.conf.py` | Address and port (`bind`), number of worker processes | |
| `webapp/etc/db_config.py` | ODBC driver and host which check the login | |
| `webapp/etc/global_cfg.py` | `C_DEFAULT_PROJECT`: project shown after the login<br>`C_COOKIE_SECURE`: send the session cookie over HTTPS only<br>`C_CORS_ALLOWED_ORIGINS`: other web sites which may call the API from a browser (default: none) | |
| `webapp/etc/logger_config.py` | Log of the web app (`webapp/log/`), log level | |
| `webapp/etc/web_constants.py` | `C_KEYS_FILE`: file of the API tokens before 2026-11 (relative to `webapp/`). Its tokens are taken over into the database at the start | [API tokens](permissions.md#api-tokens) |

`etc/constants.py` contains the defaults and is part of the repository: don't change it, put your values into `etc/settings.py`.

A file `etc/workflow.json` (all workflows in one file, the old format) still works, but it's deprecated.


## Start and stop

### Web app

```bash
webapp/service start      # also: stop, restart, status
```

```
Start service
Service is running ...
andreas    63909   63905 19 16:53 pts/0    00:00:00 gunicorn: master [wsgi:app]
andreas    63911   63909 31 16:53 pts/0    00:00:00 gunicorn: worker [wsgi:app]
...
```

The web app runs with gunicorn (`webapp/etc/gunicorn.conf.py`). By default it listens on `127.0.0.1:8080`, so it's only reachable through a [reverse proxy](#reverse-proxy) or an SSH tunnel.

Restart the web app after you have changed a file in `scripts/` or `etc/settings.py`. The settings of `Administration` → `Settings` count without restart ([settings in the web app](features/settings-in-web-app.md)).
Workflows and permissions are read again automatically.

### Processing service (optional)

By default, a stage runs in a thread of the web app and ends when the web app ends.
With the processing service, stages run in their own processes and keep running.
See [processing service](processing-service.md).

```bash
serviceapp/service start      # also: stop, restart, status
```

Start the web app first after an update: it updates the database, and the processing service doesn't start with an old database.


## Reverse proxy

Put a web server with HTTPS in front of the web app, e.g. the IBM HTTP Server (Apache):

```apache
<VirtualHost *:443>
  ServerName ireleaser.example.com

  SSLEngine on
  SSLCertificateFile    /path/to/cert.pem
  SSLCertificateKeyFile /path/to/key.pem

  ProxyPreserveHost On
  ProxyPass        / http://127.0.0.1:8080/
  ProxyPassReverse / http://127.0.0.1:8080/

  # Browsers use only HTTPS for this host for a year (mod_headers)
  Header always set Strict-Transport-Security "max-age=31536000"
</VirtualHost>
```

* `ProxyPreserveHost On` is necessary, so redirects (e.g. after the login) point to the proxy and not to `127.0.0.1`, and the check of the request origin works.
* The address has to match `bind` in `webapp/etc/gunicorn.conf.py`.
* `Strict-Transport-Security` is set by the proxy, as only it knows that the address is HTTPS. The web app itself sends the other security headers and the Content-Security-Policy ([technik.md](technik.md#content-security-policy)).
* The deployment page updates itself with server-sent events (`/api/watch_state/...`).
  If it doesn't refresh behind the proxy, make sure these responses are not compressed or buffered (e.g. by `mod_deflate`).


## Production checklist

* **HTTPS only.** The session cookie and the API tokens are sent with every request. Keep `C_COOKIE_SECURE = True` in `webapp/etc/global_cfg.py` (the default; installations of older versions may have `False` there), and set `Strict-Transport-Security` in the [reverse proxy](#reverse-proxy).
* **Two-factor authentication.** Set `C_2FA_POLICY` in `etc/settings.py` to `admins` or `required`, see [permissions](permissions.md#two-factor-authentication).
* **External address.** If the reverse proxy doesn't keep the `Host` header, set `C_EXTERNAL_URL` (e.g. `https://ireleaser.example.com`) in `etc/settings.py`: requests of the web app are only accepted from this origin.
* **`C_CSP_REPORT_ONLY` only for a short time.** It turns the Content-Security-Policy into a report (the web app logs a warning at its start). Move your custom templates to script files and remove it.
* **Keep `bind = "127.0.0.1:..."`** in `webapp/etc/gunicorn.conf.py`, so the web app is only reachable through the proxy.
* **Log level `INFO`** (the default of the templates). Debug logs contain a lot of internal data.
  Users with the permission `admin` can open the logs in the web app (menu `Logs`).
* **Never set `I_RELEASER_LOCAL_DEBUGGING`** on a server. It turns off the password check of the login, so the web app refuses to start with gunicorn if it's set.
* **Data retention.** Set `C_RETENTION_DAYS` (e.g. 730) in `Administration` → `Settings` or in `etc/settings.py` to remove finished and canceled deployments with their files in `meta/` after this many days without change, `C_RETENTION_ARCHIVE = True` to keep an archive in `var/archive/`. Log files are rotated at the start above `C_LOG_MAX_MB` (for an existing installation, copy the lines with `log_rotation` from `etc/examples/logger_config.py` and `webapp/etc/examples/logger_config.py`). See [data retention](features/data-retention.md).
* **Monitoring.** `GET /healthz` answers without login: `200 {"status": "ok", ...}` or `503` with the check which failed (database, processing service in mode `service`, free space of `var/` and `meta/` below `C_HEALTH_MIN_FREE_MB`). Use it in the monitoring tool or the health check of the load balancer.
* **Settings** (`etc/settings.py`, and those of the web app in `etc/app.json`) are checked when the web app and the processing service start: an invalid value stops the start with a message in the log, an unknown name (e.g. a typo) is a warning.
* **Failed logins.** Every wrong password is an invalid sign-on on the IBM i: after `QMAXSIGN` of them in a row (IBM default 3) the IBM i disables the profile (`QMAXSGNACN`).
  * After `C_LOGIN_MAX_FAILURES` wrong passwords of a user in a row (default 2), i-Releaser doesn't send further logins of this user to the IBM i.
    The block stays until an admin unblocks it (`Administration` → `Security` → `Blocked logins`). Unblock only when you know who has tried. Keep the limit below `QMAXSIGN`; the web app logs a warning at its start if it's 3 or more.
  * After `C_LOGIN_CLIENT_MAX_FAILURES` failed logins from a client address (default 10), its logins are blocked for `C_LOGIN_BLOCK_MINUTES` (default 15).
  * The sign-on on the IBM i ends after `C_LOGIN_TIMEOUT_SECONDS` (default 15). A sign-on without answer doesn't count for the user. At most `C_LOGIN_MAX_PARALLEL` logins per process wait for the IBM i at the same time (default 4).
  * If all admins are blocked: `sqlite3 var/app.sqlite "DELETE FROM login_failures WHERE key = 'user:<name>'"`.
* **Protect files with secrets** (`chmod 600`, owned by the user which runs i-Releaser):
  `etc/jira.json`, `etc/db_deployment.json`, `etc/notifications.json` (the settings page warns if it can be read by others: it has the URLs of the webhooks).
  Prefer environment variables for passwords and tokens (`password_env` of the DB deployment and of a mail channel, `I_RELEASER_JIRA_TOKEN`, `I_RELEASER_JIRA_CLIENT_SECRET`).
* **Treat custom data as user input.** Users with the permission `start workflow` or `edit-custom-data` can set it.
  Limit the fields with `create_fields` of the [workflow](workflow.md#create-fields).
  The same applies to the [compile list](webapi.md#create-a-deployment) (`compiles`), which every user with `start workflow` can send, to any workflow.
  [Placeholders](workflow.md#placeholders) quote or check its values, but scripts have to take care of them too.
  Only give these permissions to trusted users for workflows with a [DB deployment](db-deployment.md#security) (its column expressions are SQL).
* **Run the dependency check** regularly: `.venv/bin/pip-audit -r requirements.txt` (5 advisories of `starlette` don't apply, see [known vulnerabilities](technik.md#known-vulnerabilities)).


## Backup

| What | Where |
|---|---|
| Database: deployments, stages, steps, history, queue of the processing service, API tokens, two-factor authentication, audit log, notifications | `var/app.sqlite` (and `var/backup/`, see below) |
| Logs and generated files of each deployment | `meta/` |
| Configuration and your scripts | `etc/`, `webapp/etc/`, `scripts/`, `webapp/custom/`, `webapp/templates/custom_templates/`, `webapp/static/custom/` |

The database uses WAL mode: `var/app.sqlite-wal` and `var/app.sqlite-shm` belong to it.
Either copy all three files while the web app and the processing service are stopped, or make an online copy:

```bash
.venv/bin/python -c "import sqlite3; sqlite3.connect('var/app.sqlite').backup(sqlite3.connect('/backup/app.sqlite'))"
```

### Backups before updates

Before the web app updates the database, it copies it to `var/backup/app-{version}-{time}.sqlite` and keeps the newest copies (`C_DB_BACKUP_COUNT`, default 5).
If the copy fails, the database isn't updated and the web app doesn't start. If an update fails, the database is restored automatically.

To go back by hand: stop the web app and the processing service, delete `var/app.sqlite-wal` and `var/app.sqlite-shm`, and copy the backup to `var/app.sqlite`.


## Update

```bash
cd /apps/i-releaser
git pull
./setup3.13.sh
```

* `setup3.13.sh` installs new requirements and copies new templates. It doesn't overwrite your files:
  compare them with `etc/examples/`, `webapp/etc/examples/` and `scripts/examples/` for new settings (see the [changelog](../CHANGELOG.md)).
* Restart the web app first, then the processing service. The database is updated when the web app starts (see [backups](#backups-before-updates)).


## Logs and troubleshooting

| Log | Content |
|---|---|
| `webapp/log/` | Web app (file name from `webapp/etc/logger_config.py`), and `nohup.log` for errors during the start |
| `log/service.log`, `log/service_nohup.log` | Processing service, and errors during its start |
| Deployment page | Log of each step (stdout, stderr) and of each run of a stage. The files are in `meta/{project}/{date}/{version}/`. |

| Problem | Solution |
|---|---|
| Login: `User '...' has no permission` | Add the user (lower case) to `etc/user_permissions.json`. |
| `Because version 41 is still in status 'ready', version 42 can't be updated to status 'in process'` | Deployments of a project run in the order of their version. Finish or cancel version 41 first, or allow it with `parallel_deployment_execution_allowed` in the workflow. |
| A stage stays `in process` after the web app has been restarted | The stage ended with the web app. One minute after its last change, the stage shows a reset button. Then run it again with `Continue`. Use the [processing service](processing-service.md) to avoid this. |
| A step fails although the command worked | A `PASE` or `QSYS` command fails if it writes anything to stderr, not only if its exit code isn't 0. Set [`fail_on_stderr`](workflow.md#step-actions) to `false`. |
| A step hangs | Set [`timeout_seconds`](workflow.md#step-actions). |
| A changed script is not used | Restart the web app (and the processing service). |
| A workflow is missing | Invalid workflow files are left out. Users with `admin` see them with their error on the page `Workflows`. |
| `An unexpected error occurred. Error id: ...` | Search the id in the log of the web app. |
| `Login failed` with the right password | The login of the user or the client address is blocked after failed logins (the message doesn't say so, see [production checklist](#production-checklist)): an admin unblocks the user under `Administration` → `Security` → `Blocked logins`; a client address is unblocked after `C_LOGIN_BLOCK_MINUTES`. |
| All requests with a session get status 403 behind a proxy | Set `ProxyPreserveHost On`: the web app compares the origin of the browser with the host. |
| `Database has version ...` when the processing service starts | Start the web app first. |
