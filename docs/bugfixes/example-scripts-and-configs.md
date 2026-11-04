# Templates: example scripts and configuration files are wrong or incomplete

- **Status:** finished
- **Type:** bug
- **Priority:** P2
- **Found:** 2026-10-23, code review, partly reproduced


## Current situation

`setup3.13.sh` copies the templates into place, so new installations start with them.

**Scripts (`scripts/examples/`)**

* `target_deployment.py` calls `PROUZALIB/IRSTLIB`, a program which doesn't exist on other systems. The `SELECT` list it builds isn't used.
* `target_deployment.py`: `lib_mapping` is checked with the production library but read with the development library → `KeyError` ([target_deployment.py:63](../../scripts/examples/target_deployment.py#L63)).
* `target_deployment.py` and `save_objects.py` don't skip DB deployment tables (see [DB deployment table restored](db-deployment-table-restored-over-new-table.md)).
* `build.py` and `gen_commands.py`: `@DeprecationWarning` used as decorator replaces the functions by an exception object; calling them fails.
* `build.py` expects `make/scripts/*.sh` in the build directory. That isn't documented.

**Step actions (`etc/examples/default_step_action.json`)**

* `build` points to `build.build_all`, which doesn't exist.
* `create_object_list` and `run_build` call `scripts/cleanup.sh`, `scripts/create_build_script.sh`, `scripts/run_build.sh`, which aren't in the repository.
* `create_compile_script` is defined twice. `test_error`, `test_error_OK` (command `Wrong definition`) are test entries.

**Other templates**

* `etc/examples/object_commands.json`: wrong keys (`obj_lib` instead of `lib`, ...) and German placeholder text as commands (see [object commands](object-commands-never-run.md)).
* `etc/examples/stage_commands.json` and `webapp/etc/examples/flask_config.py` aren't used anymore. The placeholders in `stage_commands.json` are invalid (`{meta_file[general][file_name]}`, `{stage[name]}`).
* `etc/examples/workflow.json`: old format (all workflows in one file) with paths of a developer (`/home/prouzat1/...`).
* `etc/examples/user_permissions.json`: users of a developer (`prouza` with role `admin`, `prouzat1`).
* `etc/examples/constants.py`: `C_APP_VERSION = '2.0.0'` (see [database updates](db-migrations-rerun-on-every-start.md)).
* `etc/examples/jira.json` and `etc/examples/db_deployment.json` are ignored by git (`etc/**`), so they are missing in the repository, although the docs refer to them. `jira.json` has `"enabled": true`.
* `webapp/etc/examples/logger_config.py` and `etc/examples/logger_config.py` use `DEBUG` (see [session takeover via logs](session-takeover-via-logs.md)).
* The docstring of `create_deployment` describes an old object list format ([routes.py:520](../../webapp/routes/routes.py#L520)).


## Requirements

1. Each example script works on any IBM i without changes, or documents at the top what it expects (programs, directories, scripts).
2. The restore uses standard commands (`RSTOBJ`/`RSTLIB` with `SELECT`/`OMITOBJ`, `ALWOBJDIF` as needed).
3. Every entry of `default_step_action.json` points to an existing function or command. No test entries.
4. Templates contain no personal users, paths or libraries. `user_permissions.json` contains one placeholder admin user.
5. Workflow templates are single files in `etc/examples/workflows/`.
6. Unused templates are removed.
7. `jira.json` (with `"enabled": false`) and `db_deployment.json` are added to git (`git add -f`).
8. Logger templates use `INFO`.


## Acceptance criteria

- [x] Test: every `SCRIPT` entry of `etc/examples/default_step_action.json` resolves to a callable function.
- [x] Test: every template workflow passes `Workflow.validate_workflow` with the template step actions.
- [x] `grep -ri "prouza" etc/examples scripts/examples` finds nothing.
- [x] A fresh clone + `setup3.13.sh` + the template workflow runs `START` without errors (without IBM i: with fake commands).


## Non-goals

* New example scripts


## Decisions

* Replace `target_deployment.py` by `obi.py`? **No. It stays, with standard restore commands.**
