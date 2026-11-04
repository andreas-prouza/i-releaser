# Object commands are never run

- **Status:** finished
- **Type:** bug
- **Priority:** P2
- **Found:** 2026-10-23, reproduced


## Current situation

`etc/object_commands.json` defines additional commands for specific objects. They are loaded when the object list is imported (`import_objects_from_config_file` → `load_actions_from_json`) and attached to the objects.

But they never get into a stage, so they are never run:

* Object commands are copied into a stage only in `set_next_stage`, and only for stages which don't exist yet ([meta_file.py:222-242](../../modules/meta_file.py#L222)).
* Since all stages are created together with the deployment (`create_new_meta_file`), this branch is never reached.

Reproduction: object list with `prodlib|orders|file`, an object command `echo OBJECT-COMMAND-RAN` for it, run `START` and `PROD` → the command isn't part of the stages' steps and isn't run.

Further problems ([deploy_object.py:282](../../modules/deploy_object.py#L282)):

* `stages` as a list of stage names (like the template) fails: the code expects stage dicts (`stage['name']`).
* The template `etc/examples/object_commands.json` uses the keys `obj_lib`, `obj_name`, `obj_type`, but the code reads `lib`, `name`, `type`. So the template never matches.
* Object names are converted to lower case on import, the match is case sensitive.

`docs/workflow.md#object-commands` currently says that object commands aren't run.


## Requirements

1. When the object list is imported, the commands of the matching objects are added as steps to the stages which aren't finished yet.
2. `stages` is a list of stage names. Without `stages`, the command is added to all stages which have its `processing_step`.
3. Objects are matched on production library, name and type, not case sensitive.
4. Importing the object list again doesn't add the commands twice.
5. Fix the template and `docs/workflow.md`.


## Acceptance criteria

- [x] Regression test with the reproduction above: the object command runs in `START` and `PROD`, with its own status and log.
- [x] Test: `stages: ["PROD"]` → only in `PROD`.
- [x] Test: upper- and lower-case names in `object_commands.json` match.
- [x] Test: importing the object list twice → each command once per stage.


## Non-goals

* New attributes for object commands


## Decisions

* Where in the stage do they run? **Right after the step with the same `processing_step`.**
* Add them to finished stages? **No, only to stages which aren't finished.**
