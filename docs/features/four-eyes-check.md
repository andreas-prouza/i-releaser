# Four-eyes check (and the permission `deploy`)

- **Status:** draft
- **Type:** feature
- **Priority:** P3


## Current situation

The permissions `4-eyes check` and `deploy` exist and can be given in the settings, but they are not checked anywhere.
The old documentation listed a "4 eyes check" as feature. `docs/permissions.md` now says "not checked yet".


## Requirements

To be defined. A proposal:

1. A stage can require a four-eyes check (stage attribute, e.g. `four_eyes_check: true`).
2. Before such a stage can be run, a second user with the permission `4-eyes check` for this stage has to approve it.
3. The approving user has to be another user than the one who runs the stage (and than the one who created the deployment?).
4. Approval and run are recorded in the activity history.
5. Approval in the web app (button on the stage) and with the Web API.
6. A changed object list or custom data after the approval invalidates it (see open questions).
7. A [scheduled run](scheduled-stage-run.md) of such a stage can only be scheduled when the approval exists (decided 2026-11-23). The one who "runs the stage" is the user who scheduled it.


## Acceptance criteria

To be defined together with the requirements.


## Non-goals

* Approvals outside i-Releaser (e.g. in Jira)


## Open questions

* What exactly needs the second pair of eyes: running a stage, or the deployment as a whole?
* Who may not approve: the one who runs the stage, the one who created the deployment, the one who ran the previous stage?
* Does a change after the approval invalidate it? If yes: does it also cancel a run which is already scheduled, or does the scheduled run fail at its time?
* What should the permission `deploy` mean, or should it be removed?
