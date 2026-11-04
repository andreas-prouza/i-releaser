# Parallel stages overwrite each other's progress

- **Status:** finished
- **Type:** bug
- **Priority:** P0
- **Found:** 2026-10-23, reproduced on a copy of the web app


## Current situation

Each run of a stage works on its own copy of the deployment, loaded when the stage was started.
After each step, `Meta_File.save()` writes the whole deployment from that copy: all stages with their status, all steps, all objects.
If two stages of the same deployment run at the same time, each one overwrites the progress of the other with old data.

Reproduction (workflow with `parallel_deployment_execution_allowed: true`):

```
START ──► A (sleep 3; then a quick step) ──► END
     └──► B (3 × sleep 1; then a quick step) ──┘
```

1. Run `START`. Then run `A`, and `B` half a second later.
2. Result in 3 of 3 runs: `B` is `finished`. `A` stays `in process` with all steps `new`, although its log says `Finished run of stage 'A'`.

The same happens, less visibly, when a user changes something while a stage runs: edit custom data, include or exclude an object, turn off an error check.
(`docs/jira.md` already warns not to edit custom data while a stage runs.)


## Cause

* [meta_file_data.py:230](../../modules/db/meta_file_data.py#L230) `save_meta_file` writes all stages (`stage_data.save_stages`), objects and history
* [ibm_i_commands.py:117](../../modules/ibm_i_commands.py#L117) saves after each step
* [meta_file.py:209](../../modules/meta_file.py#L209) `set_next_stage` changes other stages based on the in-memory copy


## Requirements

1. A save only writes what the caller changed: the running stage (status, steps, sub-steps, run history) and the deployment fields it changed. A stage never writes other stages.
2. Changes of shared data are made against the current database state, not the in-memory copy: deployment status, activation of next stages, status of deploy objects, custom data.
   E.g. in a write transaction (`BEGIN IMMEDIATE`) which reads the rows again.
3. Two branches which finish at the same time both activate the merging stage correctly, and `after_stages_finished` sees both.
4. Changes made in the web app while a stage runs are kept and don't reset the progress of the stage.
5. Works in thread mode and with the processing service (separate processes).


## Acceptance criteria

- [x] Regression test with the reproduction above, in thread mode and with the processing service, 10 times: `A` and `B` are `finished` with all steps `finished`, `END` is `ready`, the deployment status is correct.
- [x] Test: custom data edited while a stage runs is still there after the stage has finished.
- [x] Test: two branches finish at the same time → the merging stage is `ready` once.


## Non-goals

* Running the same stage twice at the same time


## Decisions

* Fine-grained saves or optimistic locking? **Fine-grained: a stage run writes only its own stage. Shared data is changed in short write transactions.**
* Who owns the status of deploy objects? **Nobody: only changed objects are written, the last write wins per object.**
