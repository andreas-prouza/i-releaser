# Running a finished stage again blocks the deployment and the project

- **Status:** finished
- **Type:** bug
- **Priority:** P1
- **Found:** 2026-10-23, reproduced on a copy of the web app


## Current situation

`run_stage` sets the deployment to `ready` before anything is checked ([routes.py:296](../../webapp/routes/routes.py#L296)).
`check_deployment_ready_2_run` then silently returns for a stage which is `finished` or `in process`, instead of raising an error ([meta_file.py:493](../../modules/meta_file.py#L493)).
The run starts anyway: it sets the deployment to `in process`, sees the stage is finished, and ends without changing the status back.

Reproduction (workflow `START → PROD → END`):

1. Run `START` and `PROD` → `PROD` is `finished`.
2. Run `PROD` again (API call, or a second click after the stage has finished).
3. The deployment is `in process` and stays there. The web app shows no run or reset buttons for it.
4. The next deployment of the project fails: `Because version 3 is still in status 'in process', version 5 can't be updated to status 'in process'`.

The same works for a deployment which is already `finished`: it's opened again and then blocks the project.

Also, because `run_stage` sets `ready` first, the check "one stage at a time" (without `parallel_deployment_execution_allowed`) is bypassed:
a second stage can be started while another one runs.

In `check_deployment_ready_2_run`, `runable_stage.status` is used before the check `runable_stage is None` ([meta_file.py:492-500](../../modules/meta_file.py#L492)).


## Requirements

1. A stage can only be run if it's an open stage with status `ready` or `failed`. Otherwise the request fails with a clear message (status 409) and nothing changes.
2. `run_stage` doesn't set the deployment status unconditionally. Only a `failed` deployment is set back to `ready` when one of its stages is run again.
3. A `finished` or `canceled` deployment can't be run.
4. Without `parallel_deployment_execution_allowed`, a stage can't be started while another stage of the deployment is `in process` or queued.
5. Unknown stage ids give a clear error (404), not an `AttributeError`.
6. Deployments which are already stuck: `reset_deployment_status` (or a one-time database update) sets them back to `finished` if all stages are finished, otherwise to `ready`.


## Acceptance criteria

- [x] Regression test with the reproduction above: the second run of `PROD` is rejected, the deployment stays `ready`, the next deployment of the project can run.
- [x] Test: running a stage of a `finished` deployment is rejected; the deployment stays `finished`.
- [x] Test: double click (two requests at the same time) on a `ready` stage → the stage runs once, the second request is rejected.
- [x] Test: without `parallel_deployment_execution_allowed`, a second stage can't start while the first one runs.
- [x] Test: unknown stage id → 404.


## Non-goals

* [Parallel stages overwrite each other](parallel-stages-lost-update.md)
