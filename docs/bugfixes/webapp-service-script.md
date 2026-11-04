# Start script of the web app: wrong status, depends on the current directory

- **Status:** finished
- **Type:** bug
- **Priority:** P3
- **Found:** 2026-10-23, code review


## Current situation

[webapp/service](../../webapp/service):

* `status` only checks if the PID file exists. After a crash it says `running`.
* `start` refuses to start while the PID file exists, even if the process is gone.
* `stop` doesn't check if the PID file exists or the process runs; it removes the PID file even if `kill` failed.
* It only works from the `webapp` directory: the gunicorn config (`etc/gunicorn.conf.py`), the log (`log/nohub.log`) and the PID file in `gunicorn.conf.py` are relative paths.
* It prints `Activate virtual environment: .../webapp/venv/bin/activate`, but uses `../.venv`.
* `ps -ef | grep gunicorn` shows the gunicorn processes of all users.
* Unused variables (`FILE`, `LOG_LEVEL`, `PROCESS_COUNT`). The log is called `nohub.log`.

[serviceapp/service](../../serviceapp/service) already does these things right (`kill -0`, absolute paths).


## Requirements

1. `status` checks the process (`kill -0`) and shows only the processes of this installation.
2. `start` removes a stale PID file and starts. If the process runs, it refuses.
3. `stop` only kills an existing process and waits until it has ended.
4. The script works from any directory.
5. Clean up messages, variables and the log name (`nohup.log`; mention in the changelog).


## Acceptance criteria

- [x] Test (shell): after `kill -9` of the gunicorn master, `status` says `stopped` and `start` works.
- [x] Test: `cd / && /apps/i-releaser/webapp/service start` works.
- [x] Test: `stop` when nothing runs → message, exit code 0.


## Non-goals

* Running the web app as a system service (e.g. via `STRTCPSVR` or a job scheduler entry)


## Decisions

* One script for both services? **No, keep two.**
