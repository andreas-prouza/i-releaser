# Finish stages without steps automatically

- **Status:** finished
- **Type:** improvement
- **Priority:** P2


## Current situation

The last stage of a workflow (usually `END`) has no steps. It still has to be run by a user before the deployment is `finished`.

Until then the deployment stays `ready`. Deployments of a project run in the order of their version,
so the next deployment of the project can't run a stage until someone has run `END` of the previous one.

(Reproduced: after `PROD` was finished, the deployment stayed `ready` with `END` ready.)


## Requirements

1. A stage without processing steps is finished automatically as soon as it becomes `ready`, if it doesn't wait for other stages (`after_stages_finished`).
2. Then its next stages are activated as usual. If it's the last open stage, the deployment is `finished`.
3. The hooks `stage_finished` and `deployment_finished` are called as for a stage run by a user.
4. The activity history shows that the stage was finished automatically.
5. Update `docs/concepts.md` (life of a deployment).


## Acceptance criteria

- [x] Test: workflow `START → PROD → END`: after `PROD` is finished, `END` is `finished` and the deployment is `finished`, without another request.
- [x] Test: a stage without steps but with `after_stages_finished` waits until those stages are finished.
- [x] Test: hooks are called once.


## Non-goals

* Stages with steps which run automatically (that's `run_immediate`)


## Decisions

* Keep a manual `END` as an option? **No option.**
