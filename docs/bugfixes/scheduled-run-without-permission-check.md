# A queued or scheduled run doesn't check the permission when it starts

- **Status:** finished (2026-11-23; tested with `tests/test_scheduled_stage_run.py`)
- **Type:** security
- **Priority:** P2
- **Found:** 2026-11-23, code review
- **Confidential:** don't publish before the fix is released


## Current situation

The permission `run` is checked when a run is added to the queue of the processing service ([routes.py:435](../../webapp/routes/routes.py#L435)).
The job then runs in the name of the user who queued it, without a new check ([processing_service.py:156](../../modules/processing_service.py#L156)).

* A [scheduled run](../features/scheduled-stage-run.md) can be days in the future. If the user loses the permission or is removed in the meantime, the run still starts.
* The same is true, with a shorter delay, for a job which waits in the queue while the processing service isn't running.
* With the [four-eyes check](../features/four-eyes-check.md) the run also has to check that the approval is still valid at its time.


## Requirements

1. When a job starts (`run_job`, also for scheduled runs in `start_scheduled_run`), the processing service checks:
   * the user is still listed in `user_permissions.json`,
   * the user still has the permission `run` for the workflow and stage.
2. If a check fails, the job is `failed` with the reason ("User x has no permission `run` anymore"), the stage is not touched, and the deployment history shows it (like a missed scheduled run, `report_failed_scheduled_run`).
3. Removing a user (or the permission) doesn't cancel their queued jobs automatically, the check at the start is enough. The permissions page shows how many queued jobs a user has.


## Acceptance criteria

- [x] Test: a scheduled run of a user who has been removed after scheduling fails at its time with the reason, the stage stays `ready`.
- [x] Test: a scheduled run of a user who lost `run` for the stage fails the same way.
- [x] Test: a scheduled run of a user who still has the permission runs.


## Non-goals

* Checking the permission of the user at each step of a running stage.


## Decisions (2026-11-23)

* A queued run (not scheduled) which isn't run gets the entry `run_stage` "Not run (job …): …" in the history; a scheduled run the entry `scheduled_run_failed` and its hook, as for a missed time.
* Requirement 3 (number of queued jobs per user on the permissions page): not done, the failed job explains itself.


## Open questions (answered 2026-11-23)

* Requirement 3: cancel the queued jobs of a removed user right away instead? Proposal: no, the failed job is visible in the history and explains itself.
