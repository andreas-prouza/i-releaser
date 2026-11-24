# Four-eyes check (and the permission `deploy`)

- **Status:** finished (2026-11-24; tested with `tests/test_four_eyes_check.py`, `tests/test_web_browser_four_eyes.py`, not on IBM i)
- **Type:** feature
- **Priority:** P3


## Current situation

The permissions `4-eyes check` and `deploy` exist and can be given in the settings, but they are not checked anywhere.
The old documentation listed a "4 eyes check" as feature. `docs/permissions.md` now says "not checked yet".


## Requirements

Defined 2026-11-24 with the [proposal](#proposal-review-2026-11-23) (accepted):

1. A stage can require a four-eyes check (stage attribute, e.g. `four_eyes_check: true`).
2. Before such a stage can be run, a second user with the permission `4-eyes check` for this stage has to approve it.
3. The approving user has to be another user than the one who runs the stage (and than the one who created the deployment?).
4. Approval and run are recorded in the activity history.
5. Approval in the web app (button on the stage) and with the Web API.
6. A changed object list or custom data after the approval invalidates it (see open questions).
7. A [scheduled run](scheduled-stage-run.md) of such a stage can only be scheduled when the approval exists (decided 2026-11-23). The one who "runs the stage" is the user who scheduled it.


## Acceptance criteria

- [x] Test: a stage with `four_eyes_check` can't be run without approval (`409`); after the approval it runs.
- [x] Test: the user who approved can't run the stage; the user who created the deployment can't approve.
- [x] Test: approving needs the permission `4-eyes check` for the stage.
- [x] Test: a change of the custom data after the approval makes it invalid (history entry `approval_invalid`), the stage needs a new approval.
- [x] Test: a scheduled run can't be created without approval.
- [x] Test: the page shows that an approval is needed, the button `Approve` and who approved; browser test of the button.


## Non-goals

* Approvals outside i-Releaser (e.g. in Jira)


## Proposal (review 2026-11-23)

Answers proposed in the code review, to be decided by the user:

* **What needs approval:** running a stage with `four_eyes_check: true` (usually `PROD`). Per stage, so a workflow can require it for production only.
* **Who may not approve:** the user who created the deployment and the user who runs (or schedules) the stage. The approving user needs the permission `4-eyes check` for this stage.
* **What is approved:** the approval stores a hash of the object list, the custom data and the compile list. A change of one of them invalidates it (shown on the page, recorded in the history).
* **Scheduled runs:** at its time a scheduled run checks the approval again (see [run without permission check](../bugfixes/scheduled-run-without-permission-check.md)). If it's invalid, the run fails with the reason and a [notification](notifications.md) `approval_requested` is sent.
* **Permission `deploy`:** removed; a migration removes it from `user_permissions.json` (with a note in the changelog).
* **2FA:** approving needs a recent second factor ([step-up](two-factor-authentication.md#step-up)).
* **Implementation:** a rule of the use case `run_stage` of the [core redesign](core-redesign.md) (step 5), so v1, v2 and scheduled runs check it in one place.


## Decisions (2026-11-24)

* Table `stage_approvals` (`modules/four_eyes.py`): user, time, a hash of the object list (with the selection), the custom data and the compile list, and the status `valid`, `invalid` (changed afterwards) or `used` (the stage has finished: a new run needs a new approval).
* A stage can be approved while it's `new`, `ready` or `failed` (e.g. PROD while TEST runs).
* The check is part of `check_deployment_ready_2_run`, so the run in a thread, the queue of the processing service, a scheduled run (at its creation and at its time) and the Web API check it in one place. At the time of a scheduled run the user who scheduled it counts as the one who runs it.
* Approving needs a recent code of the [two-factor authentication](two-factor-authentication.md#step-up) for users who have set it up.
* `deploy` isn't offered on the permissions page anymore; an existing entry in `user_permissions.json` has no effect. `4-eyes check` can be given on all levels, also for a stage.
* Notification `approval_requested` (2026-11-24, [notifications](notifications.md#decisions-2026-11-24)): when the stage becomes `ready` without a valid approval, and when its approval becomes invalid by a change. Also a [hook event](../workflow.md#hooks). A scheduled run which can't start for a missing approval sends `scheduled_run_failed` with the reason, not a second `approval_requested`.


## Open questions (answered 2026-11-24, the proposal)

* What exactly needs the second pair of eyes: running a stage, or the deployment as a whole?
* Who may not approve: the one who runs the stage, the one who created the deployment, the one who ran the previous stage?
* Does a change after the approval invalidate it? If yes: does it also cancel a run which is already scheduled, or does the scheduled run fail at its time?
* What should the permission `deploy` mean, or should it be removed?
