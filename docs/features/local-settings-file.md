# Local settings in an untracked file

- **Status:** finished
- **Type:** improvement
- **Priority:** P3


## Current situation

`etc/constants.py` is tracked by git, but it also contains settings each installation changes (e.g. `C_PROCESSING_MODE`, settings of the processing service, git branch names, directories).
After a local change, `git pull` refuses to update it or reports a conflict (`docs/installation.md` explains the workaround with `git stash`).

It also contains the application version (`C_APP_VERSION`), which is not a setting (see [database updates](../bugfixes/db-migrations-rerun-on-every-start.md)).

`CLAUDE.md` says: all configuration belongs in `etc/`, only the templates are checked in.


## Requirements

1. Defaults are in a tracked file (e.g. `modules/settings_defaults.py`).
2. Local settings are in an untracked file in `etc/` (e.g. `etc/settings.py`), which only contains the changed values. The template is in `etc/examples/`.
3. A missing local file means: all defaults.
4. The application version is not part of the settings.
5. Existing installations: settings changed in `etc/constants.py` keep working, or the changelog explains how to move them.
6. Update `docs/installation.md` and `docs/processing-service.md`.


## Acceptance criteria

- [x] Test: without `etc/settings.py` the defaults are used.
- [x] Test: a value in `etc/settings.py` overrides the default.
- [x] After a local change of a setting, `git pull` of a new version works without conflict.


## Non-goals

* Settings in the web app


## Decisions

* Format? **Python file `etc/settings.py`, as today.**
* Move `webapp/etc/*.py` too? **No.**
