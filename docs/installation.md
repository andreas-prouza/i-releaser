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
| `etc/settings.py` | Your values for the settings of `etc/constants.py`: processing mode, processing service, git branch names, timeouts, ... | [processing service](processing-service.md#settings) |
| `etc/web_settings.json` | Processing mode changed in the web app. Overrides `etc/settings.py`. Written by the web app. | [processing service](processing-service.md#set-up) |
| `etc/workflows/*.json` | One workflow per file | [workflow configuration](workflow.md) |
| `etc/default_step_action.json` | Commands of the processing steps, for all workflows | [workflow configuration](workflow.md#step-actions) |
| `etc/object_commands.json` | Additional commands for specific objects | [workflow configuration](workflow.md#object-commands) |
| `etc/user_permissions.json` | Users, roles and their permissions. Changes are loaded automatically. | [permissions](permissions.md) |
| `etc/logger_config.py` | Log of the processing service and the command line (`log/`) | |
| `etc/jira.json` | Jira integration (optional) | [Jira](jira.md) |
| `etc/db_deployment.json` | Database connections of the DB deployment (optional) | [DB deployment](db-deployment.md) |
| `webapp/etc/gunicorn.conf.py` | Address and port (`bind`), number of worker processes | |
| `webapp/etc/db_config.py` | ODBC driver and host which check the login | |
| `webapp/etc/global_cfg.py` | `C_DEFAULT_PROJECT`: project shown after the login<br>`C_COOKIE_SECURE`: send the session cookie over HTTPS only<br>`C_CORS_ALLOWED_ORIGINS`: other web sites which may call the API from a browser (default: none) | |
| `webapp/etc/logger_config.py` | Log of the web app (`webapp/log/`), log level | |
| `webapp/etc/web_constants.py` | `C_KEYS_FILE`: file with the API tokens (hashed), relative to `webapp/` | [Web API](webapi.md#authentication) |

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

Restart the web app after you have changed a file in `scripts/` or `etc/settings.py`.
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
</VirtualHost>
```

* `ProxyPreserveHost On` is necessary, so redirects (e.g. after the login) point to the proxy and not to `127.0.0.1`, and the check of the request origin works.
* The address has to match `bind` in `webapp/etc/gunicorn.conf.py`.
* The deployment page refreshes itself with server-sent events (`/api/watch_state/...`).
  If it doesn't refresh behind the proxy, make sure these responses are not compressed or buffered (e.g. by `mod_deflate`).


## Production checklist

* **HTTPS only.** The session cookie and the API tokens are sent with every request. Set `C_COOKIE_SECURE = True` in `webapp/etc/global_cfg.py`.
* **Keep `bind = "127.0.0.1:..."`** in `webapp/etc/gunicorn.conf.py`, so the web app is only reachable through the proxy.
* **Log level `INFO`** (the default of the templates). Debug logs contain a lot of internal data.
  Users with the permission `admin` can open the logs in the web app (menu `Logs`).
* **Never set `I_RELEASER_LOCAL_DEBUGGING`** on a server. It turns off the password check of the login, so the web app refuses to start with gunicorn if it's set.
* **Failed logins.** After `C_LOGIN_MAX_FAILURES` failed logins of a user or from a client address (default 5), further logins are blocked for `C_LOGIN_BLOCK_MINUTES` (default 15).
  Keep the limit below the system value `QMAXSIGN`, otherwise failed logins can disable IBM i profiles.
* **Protect files with secrets** (`chmod 600`, owned by the user which runs i-Releaser):
  `webapp/etc/keys.json`, `etc/jira.json`, `etc/db_deployment.json`.
  Prefer environment variables for passwords and tokens (`password_env` of the DB deployment, `I_RELEASER_JIRA_TOKEN`, `I_RELEASER_JIRA_CLIENT_SECRET`).
* **Treat custom data as user input.** Users with the permission `start workflow` or `edit-custom-data` can set it.
  Limit the fields with `create_fields` of the [workflow](workflow.md#create-fields).
  The same applies to the [compile list](webapi.md#create-a-deployment) (`compiles`), which every user with `start workflow` can send, to any workflow.
  [Placeholders](workflow.md#placeholders) quote or check its values, but scripts have to take care of them too.
  Only give these permissions to trusted users for workflows with a [DB deployment](db-deployment.md#security) (its column expressions are SQL).
* **Run the dependency check** regularly: `.venv/bin/pip-audit -r requirements.txt` (5 advisories of `starlette` don't apply, see [known vulnerabilities](technik.md#known-vulnerabilities)).


## Backup

| What | Where |
|---|---|
| Database: deployments, stages, steps, history, queue of the processing service | `var/app.sqlite` (and `var/backup/`, see below) |
| Logs and generated files of each deployment | `meta/` |
| Configuration and your scripts | `etc/`, `webapp/etc/`, `scripts/`, `webapp/custom/`, `webapp/templates/custom_templates/` |

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
| `Too many failed logins` | Wait `C_LOGIN_BLOCK_MINUTES`, or fix the password of the client which keeps failing. |
| All requests with a session get status 403 behind a proxy | Set `ProxyPreserveHost On`: the web app compares the origin of the browser with the host. |
| `Database has version ...` when the processing service starts | Start the web app first. |
