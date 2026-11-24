# A finished deployment can be canceled

- **Status:** finished (2026-11-23; tested with `tests/test_review_2026_11.py`)
- **Type:** bug
- **Priority:** P1
- **Found:** 2026-11-23, code review


## Current situation

`/api/cancel_deployment/{id}` ([routes.py:512](../../webapp/routes/routes.py#L512)) doesn't check the status of the deployment.
`Meta_File.cancel_deployment` → `set_status(CANCELED)` ([meta_file.py:931](../../modules/meta_file.py#L931)) only refuses a deployment which is canceled already ([meta_file.py:193](../../modules/meta_file.py#L193)).

The deployment page hides the button for a finished deployment, but the Web API (and a script, or a double click while the last stage finishes) can still cancel it:

* The status of a deployment which is in production changes from `finished` to `canceled`. The history shows a canceled release which has actually been deployed.
* The hook `DEPLOYMENT_CANCELED` runs, e.g. a Jira transition or a rollback script.
* The commit of the deployment can be used for a new deployment again: the check in `create_deployment` ignores canceled deployments ([routes.py:676](../../webapp/routes/routes.py#L676)).

The entry "canceled" in the deployment history is written *before* the cancel ([routes.py:518](../../webapp/routes/routes.py#L518)).
If the cancel fails (e.g. already canceled), the history contains a cancel which didn't happen.


## Requirements

1. A deployment in status `finished` or `canceled` can't be canceled: `409` with the message "Deployment is already finished".
2. The check is in the model (`Meta_File.cancel_deployment`), not only in the route, so scripts can't do it either. In the [core redesign](../features/core-redesign.md) it becomes a rule of the state machine.
3. The check and the change are one atomic update (`UPDATE meta_files SET status = 'canceled' WHERE id = ? AND status NOT IN ('finished', 'canceled')`), so a cancel can't overtake the end of the last stage.
4. The history entry is written after a successful cancel. Same for the other actions which write the entry first (e.g. [routes.py:766](../../webapp/routes/routes.py#L766)).


## Acceptance criteria

- [x] Test: canceling a finished deployment with the Web API gets `409`; status, history and hooks are unchanged.
- [x] Test: a failed cancel writes no history entry.
- [x] Cancel at the same time as the last stage finishes: both are conditional updates of the same row (`claim_finished`, `claim_canceled`), only one succeeds. Not tested with timing.


## Open questions

* None.
