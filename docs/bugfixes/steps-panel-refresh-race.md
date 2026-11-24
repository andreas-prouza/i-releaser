# A refresh of the steps panel undoes what the user did meanwhile

- **Status:** finished (2026-11-24; tested with `tests/test_web_browser_deployment.py`, not on IBM i)
- **Type:** bug
- **Priority:** P3
- **Found:** 2026-11-24, by the test `test_log_dialog_keeps_the_steps` which failed once in a parallel run of the whole test suite


## Current situation (before)

The live updates of the deployment page refresh the panel of the steps of the selected stage ([live updates](../features/web-ui-live-updates.md)): when its stage changes, after a lost connection, and when the tab is shown again. `load_steps` in [deployment.js](../../webapp/static/assets/js/pages/deployment.js) took the state of the panel (open steps, filter, scroll position) *before* it requested the new steps, and restored that state when the answer arrived:

1. A step opened while the answer was on its way was closed again. The same for a filter typed or a scroll meanwhile.
2. A stage selected while a refresh of the previous stage was on its way: the refresh could arrive after the selected stage and replace it with the previous one.

On a slow server (or under the load of the parallel tests) the answer takes long enough for a click in between.


## Requirements

1. A refresh keeps the panel as it is when its answer arrives.
2. An answer which arrives after a newer one, or a refresh of a stage which isn't selected any more, is dropped.


## Acceptance criteria

- [x] Test: a step opened while the refresh is held back (Playwright route) is still open after the refresh (`test_a_step_opened_during_a_refresh_of_the_steps_stays_open`; failed before the fix every time).
- [x] Test: `START` selected while the refresh of `DEPLOY` is held back; the refresh arrives last; the panel shows `START` (`test_a_refresh_which_arrives_late_does_not_replace_the_selected_stage`; failed before the fix every time).


## Decisions (2026-11-24)

* The loads of the panel get a number. The stage selected last is remembered: a refresh of another stage is dropped, and so is an answer older than the one shown. A plain "only the newest load counts" would drop the selection of the user when a refresh starts before the selected stage has arrived.
