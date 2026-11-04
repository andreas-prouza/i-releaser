# Reset of a stage or deployment ignores stages which are still running

- **Status:** finished
- **Type:** bug
- **Priority:** P2
- **Found:** 2026-10-23, code review


## Current situation

`reset_stage_status` and `reset_deployment_status` ([routes.py:441](../../webapp/routes/routes.py#L441), [routes.py:485](../../webapp/routes/routes.py#L485))
set stages from `in process` back to `ready`, without any check:

* The web app only shows the reset button one minute after the last change of the stage ([flowchart.py:111](../../webapp/web_modules/flowchart.py#L111)). The API has no such rule.
* Neither checks the jobs of the processing service. A stage which is running in a job can be reset and started a second time.
* In thread mode a running stage can't be detected from another worker process at all.

`reset_last_finished_stage` already checks running and queued jobs (`check_reset_last_finished_stage`).


## Requirements

1. A stage can't be reset while a job of the processing service is queued or running for it (like `reset_last_finished_stage`).
2. The rule of the web app (no reset within one minute after the last change) is also checked by the server.
3. Thread mode: running stages give a sign of life (e.g. heartbeat of the stage, like the jobs of the processing service), and a stage with a recent sign of life can't be reset.
4. The error message tells why the reset isn't possible.


## Acceptance criteria

- [x] Test: reset of a stage with a running job → rejected, stage unchanged.
- [x] Test: reset of a stage changed less than a minute ago → rejected.
- [x] Test: reset of a stage whose thread has died (no sign of life) → works.


## Non-goals

* Stopping a running stage


## Decisions

* Heartbeat for thread mode? **No. The server checks the one-minute rule. The docs recommend the processing service.**
