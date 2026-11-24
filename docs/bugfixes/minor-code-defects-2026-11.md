# Minor code defects (review 2026-11)

- **Status:** ready (in progress, see [progress](#progress))
- **Type:** bug
- **Priority:** P2 (items 1–2) / P3
- **Found:** 2026-11-23, code review (items 4 and 5 reproduced)


## Current situation

| # | Defect | Where |
|---|---|---|
| 1 | **`run_immediate` runs the next stage recursively, in the run of the previous one.** An error of the next stage is raised by the run of the previous stage, which is already `finished`: its job of the processing service ends `failed`, and in thread mode the exception ends the thread. A chain of stages with `run_immediate` makes the call stack deeper with each stage. | [meta_file.py:822](../../modules/meta_file.py#L822) |
| 2 | **The import of an object list isn't atomic.** It deletes the objects first, then inserts one object per transaction. An invalid line (also an empty one: `int('')`) stops the import after the old objects are gone. | [meta_file.py:1172](../../modules/meta_file.py#L1172) |
| 3 | **`files.getJson(retry=True)` returns `None` after 5 failed attempts** instead of raising: `attempt` is at most 4, so `attempt > 4` is never true. Callers which don't expect `None` fail later with a misleading error (e.g. `keys.json`, `user_permissions.json`). | [files.py:88](../../modules/files.py#L88) |
| 4 | **Circular import.** `import modules.meta_file` as first import fails: `deploy_version` imports `meta_file` while it's loaded and uses `meta_file.Meta_File` in an annotation, which is evaluated at once. Today every entry point imports `deploy_version` first (e.g. [processing_service.py:31](../../modules/processing_service.py#L31)). | [deploy_version.py:8](../../modules/deploy_version.py#L8), [deploy_version.py:192](../../modules/deploy_version.py#L192) |
| 5 | **The permission file is read on every check.** `check_reload` only remembers the time of the last load if the file has changed, so after 2 seconds each check computes the hash of `user_permissions.json` again (twice per `is_user_allowed`, once per workflow on list pages). | [permission_config.py:193](../../modules/permission_config.py#L193) |
| 6 | **Permissions: case of names.** Users are compared in lower case for login and tokens, roles are looked up exactly ([permission_config.py:54](../../modules/permission_config.py#L54)). A role `Admin` assigned as `admin` gives nothing, without a message. A workflow entry without `general` or `stages` in the file raises `KeyError` (`500`) for every check of the workflow. | [permission_config.py:99](../../modules/permission_config.py#L99), [permission_config.py:103](../../modules/permission_config.py#L103) |
| 7 | **Mixed time zones.** A new stage gets `current_timestamp` of SQLite (UTC), later changes `datetime.now()` (local time, without zone). Jobs mix local time, UTC (`run_at`) and epoch seconds (heartbeat). The order of stages by `update_time` (e.g. last finished stage) can be wrong by the UTC offset. | [stage_data.py:33](../../modules/db/stage_data.py#L33), [stage_data.py:163](../../modules/db/stage_data.py#L163), [stages.py:77](../../modules/stages.py#L77) |
| 8 | **`etc/app.json` can be lost when two workers write it.** `write_app_settings` uses the fixed name `app.json.tmp`, `change_app_setting` reads, changes and writes without a lock. | [processing_settings.py:83](../../modules/processing_settings.py#L83) |
| 9 | **The hook `DEPLOYMENT_CREATED` runs before the deployment is complete**: before `commit` is set and before the status is `ready`. The check that a commit isn't used yet and the insert aren't atomic, two requests can create two deployments of one commit. | [meta_file_data.py:70](../../modules/db/meta_file_data.py#L70), [routes.py:676](../../webapp/routes/routes.py#L676) |
| 10 | **`set_status` writes two tables in two transactions** (`deploy_versions.details`, then `meta_files`). `deploy_versions.details.status` is read nowhere, but it's checked by `validate_deployment` on every change of the status. | [meta_file.py:200](../../modules/meta_file.py#L200) |
| 11 | **`SCRIPT` steps are found through the globals of `ibm_i_commands`.** `from scripts import *` loads every file of `scripts/` when the module is imported (a syntax error in one own script stops the web app and the service), and `globals()[name]` also finds `os`, `subprocess`, … Hooks use `importlib` with the prefix `scripts.` ([hooks.py:73](../../modules/hooks.py#L73)). | [ibm_i_commands.py:21](../../modules/ibm_i_commands.py#L21), [ibm_i_commands.py:201](../../modules/ibm_i_commands.py#L201) |
| 12 | **Ending a command after its timeout can fail.** `os.killpg` raises `ProcessLookupError` if the command ended just before; other exceptions leave the process and its pipes open (`Popen` without `with`). | [ibm_i_commands.py:273](../../modules/ibm_i_commands.py#L273) |
| 13 | **Loading a deployment creates its directory** (`os.makedirs` in `Meta_File.__init__`), also for every read in the web app. `release_branch` fails if the project is `None` (default project is applied later). | [meta_file.py:115](../../modules/meta_file.py#L115), [meta_file.py:126](../../modules/meta_file.py#L126) |
| 14 | **Settings aren't checked.** A typo in `etc/settings.py` is ignored; `C_MAX_PARALLEL_STEPS = 0` fails at the first parallel step; a negative `C_COMMAND_TIMEOUT_SECONDS` ends every command. | [constants.py:111](../../etc/constants.py#L111) |


### Dead code and unused packages

| What | Where |
|---|---|
| `itsdangerous`, `jsonschema`: imported nowhere | [requirements.txt](../../requirements.txt) |
| `watchdog`: only used by `directory_monitor_handler.py`, which only logs file events. The example `gunicorn.conf.py` doesn't use it (an own local configuration may) | [directory_monitor_handler.py](../../modules/directory_monitor_handler.py) |
| `deploy_checks.py` (uses `open_stages`, which doesn't exist), `deploy_version_sqlite.py` (uses `get_db_connection` without import) | `modules/` |
| `Deploy_Action.get_action_from_dict` calls `get_next_id`, which doesn't exist | [deploy_action.py:150](../../modules/deploy_action.py#L150) |
| `Deploy_Object_List.add_object_action`, `get_actions`, `get_layered_objects`, `sort_objects`, `get_lib_list`; `Stage.get_next_stages`, `Stage_List_list.get_stage_list_by_status`, `remove_stage`; `Meta_File.run_current_stages`, `load_version`, `get_actions` | `modules/` |
| Stage status `in preperation` and `prepare`, never set | [stage_status.py](../../modules/stage_status.py) |
| 10 permission decorators which are commented out | e.g. [meta_file.py:217](../../modules/meta_file.py#L217) |


## Requirements

1. Item 1: the stages with `run_immediate` run in a loop after the run of the stage has ended (not inside it). Each stage gets its own result; an error of the next stage doesn't change the result of the previous one.
2. Item 2: the object list is read and checked completely first (empty lines are skipped), then the objects are replaced in one transaction.
3. Item 3: `getJson` raises the last error after the last attempt.
4. Item 4: `from __future__ import annotations` in `deploy_version.py` (and the other modules of the cycle). A test imports every module of `modules/` as first import in a new interpreter.
5. Item 5: the time of the last check is also remembered if the file hasn't changed.
6. Item 6: users and roles are compared without case everywhere (stored in lower case when saved). Missing `general`/`stages` count as empty.
7. Item 7: see step 6 of the [core redesign](../features/core-redesign.md) (UTC everywhere). Until then: new stages get local time like the rest.
8. Item 8: a unique temporary file and the file lock (`files.lock`) for `app.json`.
9. Item 9: `DEPLOYMENT_CREATED` runs after the deployment is complete (commit, status `ready`). The check of the commit is part of the transaction of the insert.
10. Item 10: only `meta_files` stores the status; `deploy_versions.details` doesn't get it anymore (migration removes it).
11. Item 11: `SCRIPT` steps are resolved like hooks (`importlib`, prefix `scripts.`, only modules of `scripts/`), loaded when first used. An own script with an error only fails its steps.
12. Item 12: `Popen` in `with`; `ProcessLookupError` ignored; on any exception the process group is ended.
13. Item 13: the directory is created when something is written into it.
14. Item 14: the settings are checked at the start of the web app and the service (type, range, unknown names `C_*` in `settings.py` give a warning).
15. Dead code and unused packages are removed (see open question about `watchdog`).


## Acceptance criteria

- [ ] Test for each of the items 1–6, 8, 9, 11, 12 (the reproduction of 4 and 5 fails today).
- [ ] `grep` finds no references to the removed code; `pip-audit` and all tests pass without `itsdangerous` and `jsonschema`.


## Progress

| Item | Status |
|---|---|
| 3, 4, 5, 6 | finished 2026-11-23, tested with `tests/test_review_2026_11_modules.py` (every module is imported first in its own interpreter) |
| Dead code | finished 2026-11-23: `deploy_checks.py`, `deploy_version_sqlite.py`, the broken or unused methods and the commented decorators are removed; `itsdangerous` and `jsonschema` are removed from `requirements.txt` |
| 1 | finished 2026-11-24 with step 3 of the [core redesign](../features/core-redesign.md) |
| 2, 9 | finished 2026-11-23, tested with `tests/test_configuration.py` (an invalid list keeps the last import, empty lines are skipped; the hook sees commit and status; a commit only once per project, also with two requests at the same time: checked in the transaction of the insert) |
| 8 | finished 2026-11-23: `app.json` is written with a unique temporary file, changed under the file lock |
| 12 | finished 2026-11-23: `Popen` in `with`, the process group is ended on any error, `ProcessLookupError` ignored |
| 13 | partly: the default project is applied before the directory is named. The directory is still created when a deployment is loaded, see decisions |
| 7 | with step 6 of the core redesign |
| 10 | finished 2026-11-24 with step 1 of the core redesign: `set_status` only validates the order of the deployments, `deploy_versions.details` doesn't get the status (it was read nowhere) |
| 11 | finished 2026-11-24 with step 4 of the core redesign (`modules/scripts_loader.py`) |
| 14 | finished 2026-11-24 with step 7 of the core redesign (`modules/settings_check.py`) |


## Decisions (2026-11-23)

* `watchdog` / `directory_monitor_handler.py` stay: a local `gunicorn.conf.py` of an installation uses it. To be decided by the user.
* `jsonschema` is removed (proposal accepted).
* Unused but working helpers of `Deploy_Object_List` (`sort_objects`, `get_lib_list`, `get_layered_objects`) stay: own scripts may use them. Removed are only broken ones (`add_object_action`, `get_actions`, `get_actions_as_dict`) and unused methods of the internal classes.
* Item 13: the directory of a deployment is still created when it's loaded: scripts write their files into it and expect it to exist; the check is cheap.
* Permission errors name the permission as in the configuration (`'run'`, not `PermissionAction.RUN_WORKFLOW`).


## Open questions

* `watchdog` / `directory_monitor_handler.py`: remove, or keep as documented option for `gunicorn.conf.py`? What is it used for?
