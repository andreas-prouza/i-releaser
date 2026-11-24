# Settings in the web app

- **Status:** finished (2026-11-24; tested with `tests/test_web_settings.py`, `tests/test_settings_in_web_app.py`, `tests/test_two_factor.py`, `tests/test_web_browser_admin.py` and in headless Chromium, not on IBM i)
- **Type:** feature
- **Priority:** P3
- **Source:** question of the maintainer, 2026-11-24: move `etc/settings.py` to `etc/app.json` and maintain it in the web app?


## Current situation (before)

There are 53 settings: defaults in `etc/constants.py`, overridden in `etc/settings.py` ([local settings file](local-settings-file.md)).
Changing one needs access to the IBM i (SSH or a share of the IFS), an editor and a restart of the web app and the processing service.
Only the processing mode and `Start automatically` are changed in the web app; they are stored in `etc/app.json` and override `etc/settings.py` ([processing settings](processing-settings-in-web-app.md)).

`modules/settings_check.py` knows the type and the allowed range of every setting with a number or a choice, and checks them at the start. Most of the code reads `constants.C_...` when it needs the value, not once at import: a changed value counts from its next use. Exceptions: `C_APP_DB_FILE` (`app_sqlite.DB_FILE`) and `C_LOGIN_MAX_PARALLEL` (the thread pool of the login).


## Groups

Not all settings move. Three groups:

| Group | Settings | In the web app | Why |
|---|---|---|---|
| Start and paths, and the rest | `C_LOCAL_BASE_DIR`, `C_APP_DB_FILE`, `C_META_DIR`, `C_WORKFLOWS_DIR`, `C_SERVICE_SOCKET`, `C_SERVICE_PID_FILE`, `C_LOG_MAX_MB`, `C_LOG_BACKUPS`, ... | shown on the tab `Settings` | Needed before the web app and the database are there. A wrong value stops the web app, and then it can't be corrected in the web app. |
| Security | `C_EXTERNAL_URL` (also the origin which the CSRF check accepts), `C_2FA_POLICY`, `C_2FA_STEP_UP_MINUTES`, `C_2FA_MAX_FAILURES`, `C_LOGIN_MAX_FAILURES`, `C_LOGIN_CLIENT_MAX_FAILURES`, `C_LOGIN_BLOCK_MINUTES`, `C_LOGIN_TIMEOUT_SECONDS`, `C_LOGIN_MAX_PARALLEL`, `C_TOKEN_MAX_DAYS`, `C_WATCH_SESSION_CHECK_SECONDS`, `C_AUDIT_RETENTION_DAYS`, `C_AUDIT_FILE`, `C_CSP_REPORT_ONLY` | shown on the tab `Security` | A stolen admin session could turn off the protection (and shorten the audit log). The file needs access to the IBM i: a second barrier. Decision of the [two-factor authentication](two-factor-authentication.md): "no switch in the web app". |
| Operation | `C_RETENTION_DAYS`, `C_RETENTION_ARCHIVE`, `C_SCHEDULE_MAX_DELAY_MINUTES`, `C_MAX_PARALLEL_STEPS`, `C_SERVICE_MAX_PARALLEL_JOBS`, `C_COMMAND_TIMEOUT_SECONDS`, `C_HEALTH_MIN_FREE_MB`, `C_GIT_BRANCH_PRODUCTION`, `C_GIT_BRANCH_RELEASE` | changed on the tab `Settings` | Tuning of the daily work. A wrong value does no lasting harm and is corrected in the web app. |


## Requirements

1. A tab `Settings` in the [administration](web-ui-admin-pages.md) (`/settings/configuration`): the settings of the group *operation* with their value, where it comes from (`web app`, `etc/settings.py`, `default`), the default and a short description; a value can be saved, and reset to the file or the default.
2. The other settings are listed read only with their value and source: the group *security* on the tab `Security`, the rest on the tab `Settings`. The processing mode is shown as it counts (also when it's changed on the tab `Processing`).
3. A value is checked with the rules of `settings_check` before it's stored; an invalid value is refused with the reason (`422`), the file stays unchanged.
4. Stored in `etc/app.json`, with the name of the setting as key (like `C_PROCESSING_MODE`), written under a lock to a temporary file first.
5. Order: `etc/app.json` overrides `etc/settings.py`, which overrides `etc/constants.py`.
6. All processes use a change without restart: the web app before each request (and its daily clean up), the processing service before each look into the queue; a job process gets the values of the service when it's forked. A running stage keeps its values.
7. A change needs the permission `admin` and a recent code of the two-factor authentication (step-up), and is recorded in the audit log with the old and the new value (`setting_changed`).
8. The settings check at the start also checks the values of `etc/app.json`; an invalid value there (e.g. edited by hand) stops the start. A running process logs it and keeps the value without the web app.


## Acceptance criteria

- [x] Test: a value changed in the web app counts in the web app and in the running processing service without restart (`test_change_counts_at_once_and_is_audited`: the health check; `test_running_processing_service_uses_a_change`: the step timeout of the next job; it fails without the refresh of the service), and after a change of another process (`test_refresh_takes_a_change_of_another_process`).
- [x] Test: an invalid value is refused with the reason, the file stays unchanged (`test_invalid_value_is_refused_and_nothing_is_stored`, `test_refused_changes`).
- [x] Test: a setting of the groups *start* and *security* can't be changed in the web app, also not by the API (`test_settings_of_the_file_can_not_be_changed`, `test_refused_changes`).
- [x] Test: reset removes the value from `etc/app.json`; the value of `etc/settings.py` or the default counts again (`test_reset_uses_the_value_of_the_settings_file_or_the_default_again`).
- [x] Test: the change is in the audit log with old and new value; without a recent code it's refused (`test_change_counts_at_once_and_is_audited`, `test_step_up_for_a_setting_of_the_web_app`).
- [x] Test: an invalid value in `etc/app.json` stops the start (`test_invalid_value_of_the_file`).
- [x] Browser test: save a number and a switch, reset both (`test_change_and_reset_a_setting_in_the_form`).


## Non-goals

* Settings of the groups *start and paths* and *security* in the web app.
* The configuration files (`workflows/`, `user_permissions.json`, `notifications.json`, `jira.json`, `db_deployment.json`) in the web app.
* Removing `etc/settings.py`: it stays for the other groups and for installations which keep their configuration in files (e.g. in Git).


## Decisions (2026-11-24)

1. The groups as proposed: `C_COMMAND_TIMEOUT_SECONDS` is *operation*, `C_AUDIT_RETENTION_DAYS` is *security* (a stolen admin session shouldn't shorten the audit log). `C_EXTERNAL_URL` was proposed as *operation* (the links of notifications and Jira), but it's also the second origin which the check against requests of other sites accepts (`webmiddleware.is_same_origin`): changed by a stolen admin session to another site, that site could send requests in the name of every logged-in user. So it's *security*.
2. The web app overrides `etc/settings.py`, as for the processing mode; the page shows the source of each value.
3. The settings of the group *security* are shown read only on the tab `Security`, next to the 2FA policy and the blocked logins.
4. `C_MAX_PARALLEL_STEPS` and `C_SERVICE_MAX_PARALLEL_JOBS` count from the next group of steps or the next job; running ones keep their number.
5. `C_LOG_MAX_MB` and `C_LOG_BACKUPS` stay in the file: the log is rotated by `etc/logger_config.py` when a process starts, before `etc/app.json` is read.
6. Implementation: `modules/web_settings.py` (`EDITABLE`, `SECURITY`, `change`, `reset`, `refresh`, `load_at_start`), called by `webapp/routes/webmiddleware.py`, `modules/processing_service.py` (`run_once`) and `settings_check.check_at_start`. `refresh` compares modification time and size of `etc/app.json`, one `stat` per request. The default of a setting is read from `etc/constants.py` (a value which isn't a literal, e.g. a path, has none). Routes `GET /settings/configuration`, `POST /api/settings/{name}` (`{"value": ...}`), `DELETE /api/settings/{name}`; template `admin/configuration.html`, script `pages/configuration.js`.
