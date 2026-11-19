# New layout of the deployment page

- **Status:** draft
- **Type:** improvement
- **Priority:** P2
- **Source:** [Modernization of the web front end](web-ui-modernization.md), step 4
- **Depends on:** [Layout and styles](web-ui-layout.md), [Scripts in files](web-ui-scripts.md)


## Current situation

`show-deployment.html` (1,226 lines, 866 of them JavaScript), `flowchart.py`, `chart.js` and three templates for the steps.

* **Head:** `Projekt: erp   Workflow: deploy_2_test   Version: 6` as heading, spaced with `&nbsp;`. The status is a button which reloads the page. Cancel and reset are PNG icons without text. A clock icon at a fixed position opens the processing history.
* **Details:** a table with a table inside (id, directory, times with microseconds, the three libraries, custom data).
* **Flow chart:** buttons for the stages, placed by Bootstrap rows and columns which Python writes as text. The arrows are drawn on a canvas by generated JavaScript, again after each resize. Below each stage up to three PNG icons: run, reset, steps.
  See [stage names](../bugfixes/stage-name-breaks-deployment-page.md) and [objects table](../bugfixes/deployment-objects-table.md), number 7.
* **Steps of a stage:** a popup with two tables; the runs of a step are a table inside a cell, sub-steps a table inside a row. Wider than the screen. `Processing users`, `Lib mapping` and the directories are shown also if empty (`None`, `{}`).
* **Logs:** open in place of the steps popup. After closing, the script opens the steps again. Log lines are turned into table rows by a regular expression.
* **Actions:** `Are you sure?` → `Canceled!` → reload. The buttons are shown by status only: a user without the permission gets an error after the click.
* **Objects:** see [objects table](../bugfixes/deployment-objects-table.md).
* **History:** a list of times with a log icon each.


## Feature

```
Deployments / erp / Version 6
erp · Version 6   [failed]                                [custom] [Cancel deployment]
deploy_2_test · created 2026-11-16 18:56:47 · updated 18:56:50 · id 6

Libraries   from d000000006   backup b000000006   remote r000000006
Directory   meta/erp/2026-11-16/6  [copy]
Custom data > 3 fields                                                        [Edit]

+----------------------------------------------------------------------------------+
| (x) Stage DEPLOY failed in step broken.   [Show log] [Continue] [Run all steps]  |
+----------------------------------------------------------------------------------+

Stages                                                     4 of 6 finished ====----
 (v)--------(v)--------(v)--------(v)--------(x)--------(6)
 START      BUILD      SAVE       TRANSFER   DEPLOY     END
 finished   finished   finished   finished   failed     new
                                             ^ selected

DEPLOY  [failed]   localhost · local                          [Run stage] [Reset]
  (v) 0  quick    PASE   echo quick                           18:56:50   [Log]
  (x) 1  broken   PASE   echo restoring; ls /does/not/exist   18:56:50   [Log] [Errors]
                         check error [on]                      > 2 earlier runs
  ( ) 2  quick    PASE   echo quick                           not run

Objects (9)                                    [filter ...]   Ready: [all] [none]
  table

Activity    [Actions] [Run logs]
  table
```

### Header

* Breadcrumb, title `<project> · Version <n>`, the status as pill, the workflow, times (`datetime` filter) and the id in one meta line.
* Actions on the right, as buttons with text: `Cancel deployment`, `Reset status` (only while the deployment hangs, as today). The include `custom_templates/deployment_status.html` is shown before them.
* Libraries, directory and custom data as key and value list. Custom data: collapsed, highlighted JSON, `Edit` opens the dialog of today.
* An action is only shown if the user has the permission for it (the server checks it as before).

### Attention bar

One line which says what the deployment waits for, with the buttons for it. The first case which applies:

| Case | Text | Buttons |
|---|---|---|
| A stage failed | `Stage {name} failed in step {step}.` | `Show log` (of the failed run), `Continue`, `Run all steps` |
| A stage is in process | `Stage {name} is running: step {n} of {m}.`; with parallel steps `steps {n} and {k} of {m} at the same time`. If the next stage waits for parallel stages (`after_stages_finished`): `{next} starts when {a} and {b} are finished.` | `Show output` (of the running step) |
| A stage waits for the processing service | `Stage {name} waits for the processing service.` (and that the service isn't running, if so) | `Remove from queue` |
| A stage is ready | `Stage {name} is ready to run.` | `Run stage` |
| Deployment finished or canceled | no bar | |

Buttons are only shown with the permission `run` for that stage. With parallel stages the bar shows the first stage of the first case; the others are in the flow (e.g. one branch failed while the other is still running: the failed one).

### Stage flow

* `web_modules/stage_flow.py` computes the layout from the workflow: for each stage a column (the longest way from `START`) and a row (the first next stage stays in the row, others get rows below), and the connections. Each stage once. A connection back to an earlier stage doesn't change the columns.
* A template renders it: the stages in a CSS grid, the connections as one inline SVG from the same data. No canvas, no script to draw, no generated ids from names: `data-stage-id`.
* Parallel stages (`next_stages` with several stages, e.g. `test_wf`: `START` → `STAGE 2.1` and `STAGE 2.2` → `STAGE 3`): one row per branch. The line forks after the stage and joins before the stage which waits for them (`after_stages_finished`), in the gap between the columns, never across a stage.
* A stage shows a circle with an icon for its status (finished, failed, in process, ready, queued; otherwise its number), its name and its status. Stages which run at the same time each show theirs.
* A stage whose `after_stages_finished` are not all finished shows `waits for {stages}` (from `waiting_for` of the stage). It's `new` until then, so it has no run button (fixed in the backend: [merging stage](../bugfixes/merging-stage-ready-too-early.md)).
* The line out of a stage is green when the stage is finished. The last piece into a stage is green only when all stages before it are finished, so a join shows what the next stage still waits for.
* A click (or Enter) on a stage selects it and shows its steps below. The selected stage is in the URL (`#stage=35`), so a reload and a link keep it. Without it: the failed stage, else the running, else the first ready, else the last finished.
* A flow which is wider than the page scrolls inside its box.
* Above it: `{n} of {m} finished` with the progress bar.
* `flowchart.py`, `chart.js` and the canvas are removed. The images `run-green.png`, `undo.png`, ... stay in `static/assets/img/`: custom templates use them (e.g. `undo.png` for a rollback button).

### Steps of the selected stage

* Part of the page, not a popup. Loaded from `GET /show_details/{meta_file_id}/stage/{stage_id}` (a rendered part of the page).
* Head: name, status, description; host, local or remote, and only if set: remote dir, build dir, library mapping. Who ran or reset the stage (last entry, all entries on request). Buttons `Run stage` (asks `Continue` / `Run all steps from the beginning`, as today) and `Reset` (as today: a hanging stage, or the last finished stage).
* One row per step: status icon, sequence, name, type (`PASE`, `QSYS`, `SCRIPT`), local or remote, the command in one line, the time of the last run, buttons `Log` and `Errors` (only if there is output).
  * Opened: the full command (one part per line, with a copy button), the switch `check error` (only with the permission `change check error`, disabled in finished and canceled deployments), earlier runs.
  * A failed step is open.
* Sub-steps are rows below their step, indented, collapsed if there are more than 10 and none failed.
* Parallel steps (`parallel`, `parallel_group`, see [workflow](../workflow.md#parallel-steps)): the steps of a group are shown together, with a bar on the left and a line `Group {name}: {n} steps run at the same time, the next step waits for all of them`. Several steps of a group can be running at once, each with its own status, time and log. The same for parallel sub-steps of a script.
* Empty values are left out or shown as `–`.

### Logs

* A dialog over the page; the steps stay as they are behind it.
* Title: step and time of the run. `Output` and `Errors` as tabs. The text in monospace, unchanged (no table rows), with `Wrap lines`, `Copy` and `Download`.
* The same dialog for the logs of the deployment history.

### Objects

The requirements of [objects table](../bugfixes/deployment-objects-table.md), and:

* The rows come from `GET /api/deployment_objects/{meta_file_id}` (JSON), so the table can be refreshed without losing sorting, filters and the page.
* Columns: Ready (switch), Level, Production library, Target library, Name, Type, Attribute, Source only (as check mark), Status (pill).
* Without objects the section shows `This deployment has no objects`.

### Activity

* Two tabs: `Actions` (the processing history: time, user, action, stage, details) and `Run logs` (the deployment history: time, `Log`).
* Both as tables, newest first.

### Server

* `show_details_by_id` passes prepared data: the layout of the flow, the attention bar, the selected stage and which actions the user may use. The templates contain no permission logic.
* New: `GET /show_details/{meta_file_id}/stage/{stage_id}`, `GET /api/deployment_objects/{meta_file_id}`, `POST /api/set_objects_ready/{meta_file_id}`. All with the permission checks of the existing endpoints.
* `/show_details/{id}` and `/show_details/{project}/{version}` stay. `/api/get_stage_steps_html` stays until the next major version (it's listed in [webapi.md](../webapi.md)), marked as deprecated.


## Acceptance criteria

- [ ] Test `stage_flow`: a sequence; parallel branches which join (`test_wf`, `parallel_example`); a stage reached from two stages exists once; a connection back to an earlier stage ends; a workflow without `next_stages`; branches of different length (a line that skips a column runs in a free row, not across a stage).
- [ ] Test: the colours of the lines of a join: one branch finished, the other running → the line into the next stage is grey.
- [ ] Test: the steps of a stage with a parallel group: the group line, two running steps, the step after the group `new`.
- [ ] Test: the page of workflows with the stage names of [stage names](../bugfixes/stage-name-breaks-deployment-page.md).
- [ ] Test: the attention bar for each case of the table, and none for finished and canceled deployments.
- [ ] Test: users without `run`, `cancel workflow`, `edit-custom-data` or `change check error` don't get the buttons (users `intern`, `runner`, `stranger` of the tests); with the permission for one stage only, only there.
- [ ] Test: the steps of a stage: sub-steps, earlier runs, commands with `<`, `&` and quotes as text, `Log` only with output, `403` without `read`.
- [ ] Test: `deployment_objects`: all objects, `403` without `read`. The criteria of [objects table](../bugfixes/deployment-objects-table.md).
- [ ] Test: no `None` and no microseconds in the page of a deployment with empty values.
- [ ] Test: the custom template `deployment_status.html` is included in the header.
- [ ] Browser tests (or manual checks, see [browser tests](web-ui-browser-tests.md)):
  * select a stage → its steps; the selection survives a reload;
  * run a stage with `Continue` → one dialog, one toast, the status changes;
  * open and close a log → the steps are unchanged, an opened step stays open;
  * cancel a deployment → one dialog; canceling the dialog shows nothing;
  * edit custom data;
  * no error in the console, no horizontal scrolling at 1440 px, 1024 px and 768 px.
- [ ] Measurement: the page of a deployment with 20 stages and 500 objects is not slower than today (59 ms, see [performance](performance-blocking-handlers.md#measurements)). Numbers in this file.
- [ ] Docs: [webapi.md](../webapi.md) (new endpoints), [scripts.md](../scripts.md#web-app-extensions), screenshots of [README.md](../../README.md).


## Non-goals

* Updates without reload: [live updates](web-ui-live-updates.md). Until then the page reloads as today.
* Stopping a running stage
* Durations of steps and stages, or a time line of the deployment: only the start of a run is stored (`action_run_history.create_time`)
* Showing the compile list


## Open questions

1. Steps as part of the page below the flow (**recommended**: logs then need only one dialog, and the steps can be linked), or a dialog as today?
2. Run and reset: only in the attention bar and in the head of the steps (**recommended**), or also below each stage of the flow as today?
3. Objects: the level as a column with the default order by level (**recommended**), or headings per level (needs the group extension of bootstrap-table, and a heading can't be sorted or filtered)?
4. Processing history: as tab `Actions` in the page (**recommended**), or behind a button as today?
5. Actions without permission: hidden (**recommended**), or shown disabled with the reason as tooltip?
6. The mockup (the canvas [i-Releaser web UI mockup](https://claude.ai/artifact/HQqeugdfJgXrLDZLn2tRX7), artboards for a failed linear deployment and for `test_wf` with parallel stages and a parallel step group) of this page (question 2 of the [modernization](web-ui-modernization.md#open-questions)).
