# Command line `deployment.py` doesn't work

- **Status:** finished
- **Type:** bug
- **Priority:** P2
- **Found:** 2026-10-23, reproduced


## Current situation

`deployment.py` was still from the time of the JSON meta files:

* `-a create` fails with a circular import (`modules.meta_file` is imported before `modules.deploy_version`).
  Even with the right import order it only creates a `Meta_File` in memory (id `None`) and saves nothing (`create_new_meta_file` isn't used).
* `-a run` passes the stage **name** where a stage id is expected, and then reads the attribute `mf.open_stages`, which doesn't exist.
* The run has no user, so the activity history records `None`, and no permission is checked.

`docs/installation.md` says the command line is outdated.


## Requirements

Depends on the open question. If it's kept:

1. `create` creates a deployment like `POST /api/start_workflow` (workflow, optional commit, object list, custom data as JSON).
2. `run` runs a stage by name (or id) of a deployment, given by project and version.
3. The user is the user profile which runs the command. It has to be listed in `etc/user_permissions.json` and needs the same permissions as in the web app.
4. Exit code 0 only if the action succeeded. Output in JSON (`--info-output`) as today.
5. Document it in `docs/installation.md`.

If it's removed: delete `deployment.py` and its mention in the docs.


## Acceptance criteria

- [x] `deployment.py` is removed and not mentioned in the docs anymore.


## Non-goals

* An interactive command line


## Decisions

* Fix or remove `deployment.py`? **Remove it. The Web API covers the same.**
