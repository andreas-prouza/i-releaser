# A stage name can turn off all buttons of the deployment page

- **Status:** finished (2026-11-17, fixed with [values run as script](web-values-run-as-script.md); tested with `tests/test_web_pages.py` and in headless Chrome)
- **Type:** bug
- **Priority:** P2
- **Found:** 2026-11-16, analysis of the web front end; reproduced in Chrome on a copy of the web app


## Current situation

The flow chart of the deployment page is HTML and JavaScript which Python builds as text ([flowchart.py](../../webapp/web_modules/flowchart.py)).
Each stage gets an id from the base64 code of its name ([flowchart.py:42](../../webapp/web_modules/flowchart.py#L42)), and this id is also used as the name of a JavaScript variable ([flowchart.py:250](../../webapp/web_modules/flowchart.py#L250)):

```js
let flow_QS0+Qg = document.getElementById("flow_QS0+Qg");   // stage "A->B"
```

Base64 contains `+` and `/`. They appear for `>`, `?` or `~` as every third character of the name, and for some characters outside ASCII:

| Stage name | Id |
|---|---|
| `A->B` | `flow_QS0+Qg` |
| `Deploy -> Prod` | `flow_RGVwbG95IC0+IFByb2Q` |
| `QA?` | `flow_UUE/` |

Reproduced with a workflow with the stage `A->B`: `SyntaxError: Unexpected token '+'`.
The generated lines are part of the one script of the page ([show-deployment.html:401](../../webapp/templates/overview/show-deployment.html#L401)), so the whole script is not run:
no button works on any deployment of this workflow (run, cancel, reset, steps, logs, custom data), and the auto refresh doesn't start. There is no message.

A `'` in a stage name breaks the `onclick` of the run and reset buttons in the same way (see [values run as script](web-values-run-as-script.md), number 6).


## Requirements

1. Any stage name the workflow check accepts works on the deployment page.
2. Stages are identified by their database id (`data-stage-id="35"`), not by a code of their name.
3. Python doesn't generate JavaScript. **Open:** `flowchart.py` still generates the lines which connect the stages, now with names from the ids (`flow_stage_35`). It's removed with the [stage flow](../features/web-ui-deployment-page.md#stage-flow).


## Acceptance criteria

- [x] Test: the deployment page of a workflow with the stages `A->B`, `QA?`, `It's done`, `Prüfung <1>` and `STAGE 2.1` is rendered, the names are escaped, and the page contains no JavaScript generated from them.
- [x] Manual check in headless Chrome: on the page of a workflow with the stages `A->B`, `It's <b>x</b>` and `STAGE 2.1` the steps of a stage and the dialog to run a stage open. No error in the console.
- [x] Changelog entry.


## Non-goals

* Restricting the characters of stage names


## Open questions

None. The new [stage flow](../features/web-ui-deployment-page.md#stage-flow) fixes this by design. If it isn't done soon: use `stage.id` for the ids, and `data-*` attributes instead of generated variables (small change in `flowchart.py` and `chart.js`).
