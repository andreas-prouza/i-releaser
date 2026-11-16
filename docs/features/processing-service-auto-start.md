# Start the processing service automatically with the web app

- **Status:** finished
- **Type:** improvement
- **Priority:** P3


## Current situation

In mode `service` the [processing service](../processing-service.md) has to be started by hand:
on the command line (`serviceapp/service start`) or in the web app (`Settings` → `General` → `Processing of stages`).

After a restart of the system (IPL) or a crash of the service, stages stay in the queue (`queued`) until someone notices it and starts the service.


## Requirements

1. On the settings page (`Settings` → `General` → `Processing of stages`) there is a checkbox `Start automatically` next to the buttons `Start`, `Stop`, `Restart`. Only users with the permission `admin` can change it.
2. If it's ticked and the processing mode is `service`, the web app makes sure the service is running:
   * when the web app starts, after the database has been updated (`app_sqlite.check_updates()`), otherwise the service refuses to start,
   * and every `C_SERVICE_WATCHDOG_INTERVAL` seconds while the web app is running (watchdog).
3. In mode `thread` nothing happens.
4. After `Stop` the auto start is paused until the next `Start` or `Restart`. The checkbox stays ticked. The settings page shows that the auto start is paused.
5. The service is started only once, even though several workers of the web app check at the same time (gunicorn: `workers = 5`).
6. A failed start doesn't stop the web app. It's logged, and the settings page shows the service as stopped as before.
7. The check doesn't delay the start of the web app or a request (`serviceapp/service start` waits at least 1 second).
8. The service keeps running when the web app ends (like a start in the web app).


## Acceptance criteria

- [x] Test: auto start on, mode `service`, service stopped → after the start of the web app the service is running.
- [x] Test: auto start off → the service is not started.
- [x] Test: mode `thread` → the service is not started.
- [x] Test: service already running → no second service is started.
- [x] Test: watchdog: the service ends (killed) → it's started again with the next check.
- [x] Test: `Stop` (web app and `./service stop`) → the watchdog doesn't start it again; after `Start` it does.
- [x] Test: several workers / parallel starts → exactly one service is running.
- [x] Test: a second `serviceapp/service.py` ends immediately while one is running (lock).
- [x] Test: start of the service fails → the web app starts anyway, error in the log.
- [x] Test: users without `admin` get `403` when they change the checkbox; the action needs `POST`.
- [x] Test: an existing `etc/web_settings.json` is taken over into `etc/app.json` (mode is kept).
- [x] Docs: [processing-service.md](../processing-service.md) (set up, settings table, "What happens if ...", systemd), [webapi.md](../webapi.md).

Tests: `tests/test_service_auto_start.py`, `tests/test_processing_settings.py`, `tests/test_processing_service.py`.


## Non-goals

* Starting the service at IPL without the web app (e.g. autostart job on IBM i)
* Starting the web app automatically
* Support for systemd (see decisions)


## Possible bug found during the analysis

Two services can run at the same time, if `serviceapp/service start` runs twice in parallel (e.g. two admins click `Start`, or the auto start of several workers):

* `serviceapp/service`: between the check `is_running` and `nohup ... &` a second call can start another service.
* `Service.start()` ([modules/processing_service.py](../../modules/processing_service.py)): checks `notify()`, then removes the socket and binds a new one. The second service removes the socket of the first one and overwrites the PID file.

Consequences:

* A job is **not** run twice: `claim_next_job()` claims a job atomically (`UPDATE ... WHERE status = queued`).
* The first service is an orphan: no socket (no wake up, only polling), not in the PID file, so `./service stop` and the settings page don't see it.
* Up to twice `C_SERVICE_MAX_PARALLEL_JOBS` stages run at the same time.

Fixed with this feature (see decisions).


## Decisions (2026-11-16)

* **Setting:** only the checkbox on the settings page, **default off** (no new setting in `etc/settings.py`). So nothing changes until an admin ticks it.
* **Storage:** `etc/web_settings.json` is renamed to **`etc/app.json`**: one file for all settings changed in the web app (processing mode and auto start).
  An existing `etc/web_settings.json` is renamed at the start of the web app, so an installation keeps its mode.
  The setting `C_WEB_SETTINGS_FILE` is replaced by `C_APP_SETTINGS_FILE`.
* **Watchdog:** at the start of the web app **and** a background task (like `delete_expired_sessions`), every `C_SERVICE_WATCHDOG_INTERVAL` seconds.
  New constant `C_SERVICE_WATCHDOG_INTERVAL = 60` in `etc/constants.py`, can be overridden in `etc/settings.py`. The check is cheap (`notify()`: one datagram to the socket).
* **After `Stop`:** the auto start is paused until the next `Start` / `Restart`. The checkbox stays ticked.
  `serviceapp/service stop` creates the marker file `var/processing-service.stopped`, `start` (and so `restart`) removes it.
  The buttons of the web app call the same script, so a stop on the command line pauses the auto start the same way.
  It's runtime state, so it's in `var/` and not in `etc/app.json`. The watchdog and the start of the web app don't start the service while the file exists.
* **Lock:** part of this feature. The service holds an exclusive file lock (`C_SERVICE_LOCK_FILE`, `var/processing-service.lock`) as long as it runs; a second service ends immediately.
  * `fcntl.lockf` (POSIX record lock) instead of `flock`: it's available in PASE on IBM i, and it belongs to the process, so a forked job process doesn't hold it.
    A job which still runs after the stop of the service doesn't block the start of a new one.
  * The auto start uses its own lock (`var/processing-service.lock.start`): the lock of the service can't be held by the web app while the service starts.
    A worker which doesn't get it skips the check; the next check is soon enough.
  * The auto start waits up to 10 seconds until the started service listens (`serviceapp/service` waits only 1 second, loading the scripts may take longer on IBM i).
    The start lock is kept meanwhile.
* **Implementation:** `ensure_service_running()` in `modules/processing_settings.py`, called by the task `watch_processing_service()` of `webapp/index.py` in a thread.
  New route `POST /api/set_service_auto_start/{enabled}`.
* **systemd:** only documented. If the web app runs under systemd (`KillMode=control-group`), a service started by the web app is killed with it.
  There: run the service as its own unit and leave the auto start off. Not relevant on IBM i.


## Open questions

None.
