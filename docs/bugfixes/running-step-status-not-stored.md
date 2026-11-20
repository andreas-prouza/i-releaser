# A running step is not shown as running

- **Status:** finished (2026-11-19; tested with `tests/test_running_step_status.py`, not on IBM i)
- **Type:** bug
- **Priority:** P3
- **Found:** 2026-11-19, with the [deployment page](../features/web-ui-deployment-page.md): a stage with a group of parallel steps, which run 4 seconds


## Current situation

* `IBM_i_commands._run_action` ([ibm_i_commands.py](../../modules/ibm_i_commands.py)) stores the status of a step when it has ended (`finished` or `failed`). While it runs, the step stays `new` in the database.
* The web app, the Web API (`get_meta_file_json`) and the OBI extension read the database: they never see a step `in process`. For a long step (a restore of 20 minutes) nobody can see which step runs.
* The deployment page shows for a running stage `Stage DEPLOY is running: 3 of 9 steps finished.` instead of `step 4 of 9`, and can't mark the steps of a parallel group which run at the same time. The page shows both as soon as the status is stored (tested with prepared data in `tests/test_deployment_page.py`).


## Requirements

1. A step is stored as `in process` when it starts (one `UPDATE` of its row, not the whole deployment), and as before when it has ended.
2. Parallel steps: each step of a group is `in process` while it runs.
3. A step which stays `in process` after a crash is run again with `Continue` (as a `new` step today).


## Acceptance criteria

- [x] Test: while a step runs, `get_meta_file_json` returns it `in process`; the steps before it `finished`, after it `new`.
- [x] Test: a group of two parallel steps: both `in process` at the same time (and the deployment page says `steps 1 and 2 of 3 at the same time`).
- [x] Test: a stage which was stopped while a step was `in process` runs the step again with `Continue`.
- [x] Measurement: the time per step grows by less than 2 ms. A stage with 120 `echo` steps, thread mode, 2026-11-19: before 1.8 – 2.5 ms per step, after 2.0 – 2.1 ms (within the noise).


## Implementation

* `IBM_i_commands._run_action` sets `in process` when a step starts and stores only its status (`actions_data.save_action_status`, one `UPDATE`). When it has ended, the deployment is saved as before.
* A sub-step which is not in the database yet (added by a script just before) is stored with the deployment, as before.
* `tests/test_parallel_steps.py`: a parallel step which has been started is `in process` (or `new` while its thread starts), not `new` only.


## Non-goals

* Showing the output of a running step while it runs


## Decisions (2026-11-19)

* To be done, although the [modernization](../features/web-ui-modernization.md#non-goals) excludes changes of the processing of stages: one database update per step, so the deployment page (and later the OBI extension) can show the running step.


## Open questions

None.
