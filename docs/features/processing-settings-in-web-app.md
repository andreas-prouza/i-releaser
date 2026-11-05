# Processing mode and processing service in the web app

- **Status:** finished
- **Type:** improvement
- **Priority:** P3


## Current situation

The processing mode is `C_PROCESSING_MODE` in `etc/settings.py`. A change needs a restart of the web app (the value is read once at import).
The [processing service](../processing-service.md) is started and stopped on the command line (`serviceapp/service start|stop`).
`Settings` → `General` → `Processing of stages` only shows both.


## Requirements

1. Users with the permission `admin` can change the processing mode on the settings page, without a restart of the web app.
2. They can start, stop and restart the processing service there.
3. All workers of the web app use the new mode for the next stage.
4. A started service keeps running when the web app ends.


## Acceptance criteria

- [x] Test: after a change of the mode, the next stage runs in the new mode (thread / service).
- [x] Test: users without `admin` get `403` for all new actions.
- [x] Test: the actions need `POST` (CSRF, like the other actions).
- [x] Test: the service started by the web app keeps running when the web app is stopped.
- [x] Docs: [processing-service.md](../processing-service.md), [webapi.md](../webapi.md).

Tests: `tests/test_processing_settings.py`.


## Non-goals

* Other settings in the web app
* Starting the service automatically (e.g. with the web app or at IPL)


## Decisions (2026-11-05)

* Switch to `thread` while stages are in the queue of the service: **not possible.** Running jobs don't matter, they finish on their own.
* Start of the service: **the web app runs `serviceapp/service start|stop|restart`** (fixed command, no user input) in its own session, and shows the output.
* Switch to `service` while the service is stopped: **allowed**, with a warning and the button `Start`.
* Who changed it: **a log entry (`INFO`) with the user.** No history table.
* Where the mode is stored: **`etc/web_settings.json`** (untracked, in `etc/` like all configuration). The web app doesn't write Python code into `etc/settings.py`.
  * The value in `etc/web_settings.json` overrides `etc/settings.py`, which overrides the default in `etc/constants.py`.
  * It's read whenever a stage is started, so all workers use the new mode without a restart.
  * The settings page shows where the value comes from.
* Implementation: `modules/processing_settings.py`. `serviceapp/service` uses the Python of the web app (`I_RELEASER_PYTHON`), otherwise `.venv/bin/python` as before.


## Open questions

None.
