# Start time of the web app and the processing service

- **Status:** finished (2026-11-24; tested with `tests/test_start_times.py`, `tests/test_admin_pages.py` and in headless Chromium, not on IBM i)
- **Type:** feature
- **Priority:** P3
- **Source:** request of the maintainer, 2026-11-24


## Current situation

The settings pages show whether the processing service is running, but not since when. When the web app was started can't be seen at all.
So after an update you can't tell from the web app whether the web app and the service have been restarted (and run the new code), or whether the auto start has restarted a crashed service.

`webapp/index.py` writes a row into the table `app_info` at each start of a web app process (version, process id, `start_time`). The processing service writes its process id into `var/processing-service.pid` at its start and removes the file when it stops.


## Requirements

1. **Administration → System** (before: Settings → General), part `Installation`: `Web app started` and `Processing service started`.
2. **Administration → Processing**: the start time beside the status of the processing service.
3. The times are shown in the time zone of the browser (like scheduled runs).
4. Web app: gunicorn starts several worker processes, each loads the web app. The time is the start of the oldest running process of this web app, so it's the same on every worker and changes with a restart of the web app.
5. Processing service: only while it's running (a service which has been killed leaves its pid file behind); the page also shows its process id.


## Acceptance criteria

- [x] Test: the start of the web app is the oldest start of its running processes; processes which have ended and processes of another web app (another parent process) don't count (`tests/test_start_times.py`).
- [x] Test: the start of the processing service is the time of its pid file, nothing without the file (`tests/test_start_times.py`).
- [x] Test: the general settings show the start of the web app, the processing page the start of the running service, both as `<time>` in UTC for the browser (`tests/test_admin_pages.py`).


## Non-goals

* A history of the starts (the log has the line `Processing service started`).
* The start times in `/healthz`.


## Decisions (2026-11-24)

* Web app: `app_info` stores the parent process id too (the gunicorn master). The start is the oldest `start_time` of the rows whose process still runs and which have the same parent as the asking process, or which are that parent (gunicorn with `preload_app`). No access to the process list of the system: that differs between Linux and IBM i (PASE).
* A process id which is used again (e.g. after a restart of the system) could make the time too old: only the newest row of each process id counts. Rows of versions before 4.1.0 have no parent and only count for the own process and the parent.
* Processing service: the time of the pid file (set when the service starts). The format of the file stays the same (only the process id), as `serviceapp/service` reads it.
* The page shows the time to the minute in the time zone of the browser, its tooltip the exact time in UTC (macro `local_time`; `kv_list` shows a value `{'time': ..., 'note': ...}` this way).
