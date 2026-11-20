# A stage which waits for parallel stages is `ready` too early

- **Status:** finished (2026-11-19; tested with `tests/test_stage_flow.py`, `tests/test_web_deployment.py` and the screenshots, not on IBM i)
- **Type:** bug
- **Priority:** P2
- **Found:** 2026-11-19, with the screenshots of `tests/screenshots.py` (workflow with `START` → `STAGE 2.1` and `STAGE 2.2` → `STAGE 3`)


## Current situation

A stage with `after_stages_finished` (e.g. `STAGE 3` after `STAGE 2.1` and `STAGE 2.2`) becomes `ready` as soon as the first of these stages is finished: `set_next_stage` activates every next stage ([meta_file.py:256](../../modules/meta_file.py#L256)).
Only running it checks the other stages and refuses it (`StageNotReadyException`, [meta_file.py:634](../../modules/meta_file.py#L634)).

* The web app shows the run button for it. A click ends with the error "still waiting for other stages".
* The OBI extension shows "Stage STAGE 3 is ready to run" with **Run stage** (it takes the first `ready` stage).
* Clients can't tell why a `new` or `ready` stage doesn't run.
* [concepts.md](../concepts.md#parallel-branches) says the merging stage becomes `ready` only after the stages in `after_stages_finished`. The test `test_stage_without_steps_waits_for_its_stages` asserts `ready`.

There is no own status for "reached, but waiting" (decision of 2026-11-19, see below).


## Requirements

1. A stage becomes `ready` only when all stages in its `after_stages_finished` are finished. Until then it stays `new`.
2. Of several branches which finish at the same time, exactly one activates the stage: the check is part of the database update which sets `ready` (like `activate_stage` today).
3. The automatic run of the merging stage (`run_immediate`, or a stage without steps) happens when the last branch is finished.
4. Reset of the last finished stage: a next stage which waits for the reset stage is set back to `new`, also if another finished stage leads to it.
5. The Web API returns for each stage `waiting_for`: the names of the stages in `after_stages_finished` which are not finished yet. Empty for finished stages and stages which wait for nothing.
6. The deployment page shows no run button for such a stage (follows from 1), and names the stages it waits for in the tooltip of the stage.
7. Deployments which are in progress when the update is installed are not changed: a merging stage which is `ready` already stays `ready` (running it is refused as before).


## Acceptance criteria

- [x] Test: one branch finished → the merging stage is `new`, `waiting_for` names the other branch, running it is refused; the deployment is `ready`.
- [x] Test: both branches finished → the merging stage without steps is finished, the deployment is finished (as before).
- [x] Test: a merging stage with steps and `run_immediate` runs when the last branch is finished, not before.
- [x] Test: `after_stages_finished` lists only one of the branches: the stage becomes `ready` when that one is finished, independent of the other.
- [x] Test: the activation in the database, with the stages it waits for not finished → no change; all finished → `ready`; 10 threads at the same time → activated once.
- [x] Test: reset of a branch after the merging stage became `ready` → the merging stage is `new` again.
- [x] Test: `waiting_for` in `/api/get_meta_file_json`.
- [x] Docs: [concepts.md](../concepts.md#parallel-branches), [webapi.md](../webapi.md). Changelog entry.


## Implementation

* `stage_data.activate_stage(stage_id, wait_for)`: the `UPDATE` to `ready` counts the finished stages of `wait_for` in a subquery. `set_next_stage` passes `after_stages_finished`. The finishing stage is saved as `finished` before (`Stage.set_status` writes at once), so the last branch sees all of them.
* `Meta_File.get_waiting_for(stage)` and `waiting_for` in `get_all_data_as_dict` (open and processed stages).
* `reset_last_finished_stage`: a next stage which waits for the reset stage goes back to `new`.
* `flowchart.py`: tooltip `Waits for ...` on the stage.
* Five of the new tests fail with the code before the fix; the automatic run of the merging stage worked before and still works.


## Non-goals

* A new stage status `waiting`
* Changes in the OBI extension (it can use `waiting_for` later)


## Decisions

* New status `waiting`, or `new` plus `waiting_for`? **`new` plus `waiting_for` (2026-11-19).** No new transitions and no change of the status values which clients (OBI extension, Jira) know; the reason is computed from the stages, so it can't be outdated after a reset.


## Open questions

None.
