# Deployment page: defects of the table "Objects to deploy"

- **Status:** finished (2026-11-19; tested with `tests/test_web_pages.py` and in headless Chrome on a copy of the web app, not on IBM i)
- **Type:** bug
- **Priority:** P2
- **Found:** 2026-11-16, analysis of the web front end; reproduced in Chrome on a copy of the web app (deployment with 9 objects in 4 levels)


## Current situation

| # | Defect | Cause |
|---|---|---|
| 1 | `Loading, please wait` is always shown above the table. Filters and paging look unstyled. | The page loads the script of bootstrap-table, but not its stylesheet ([show-deployment.html:347](../../webapp/templates/overview/show-deployment.html#L347)) |
| 2 | `Showing 1 to 10 of 13 rows` for 9 objects. The rows `Level 1`, `Level 2`, ... are counted, sorted and filtered like objects: after a sort by name they are somewhere in the table. | The level headings are table rows ([show-deployment.html:296](../../webapp/templates/overview/show-deployment.html#L296)), bootstrap-table reads them as data |
| 3 | The switch in the header (all objects ready): turning it on shows `An unexpected error occurred. Error id: ...`, and the web app logs a `KeyError` for each level. | `toggleAll` sends a request for each level row, without library and name ([show-deployment.html:1182](../../webapp/templates/overview/show-deployment.html#L1182)) |
| 4 | The same switch sends a request for each finished object, answered with `409`. | Finished objects can't be changed, but they are not left out |
| 5 | The same switch: an object whose name contains `'`, `&` or `<` is not found (`404`). | The name is read from the HTML of the cell (`o&#39;brien`), and the state of the switch is found by searching the HTML for `checked=""` |
| 6 | The same switch sends one request per object, one after the other, and writes one entry to the processing history for each. With 500 objects that takes a while, without progress. | No request for several objects |
| 7 | The page is wider than the window (254 px at 1440 px), so it scrolls sideways. | The canvas of the flow chart gets the width of the window, but starts right of the navigation ([show-deployment.html:396](../../webapp/templates/overview/show-deployment.html#L396)) |
| 8 | A switch can be clicked for finished objects and in finished or canceled deployments. The error comes after the click. | The state isn't used to disable the switch |


## Requirements

1. The table uses bootstrap-table with its stylesheet (see [architecture](../architektur.md#gui)).
2. The table contains only objects. The level is a column; the default order is by level.
3. "All ready" / "none ready" applies to the objects which match the current filter, in **one** request: `POST /api/set_objects_ready/{meta_file_id}` with the objects and the new value.
   * Permission and conditions as for a single object (`run`, deployment not finished or canceled).
   * Finished objects are left unchanged and reported in the response.
   * One entry in the processing history, with the number of objects.
4. Objects are identified by their values from `data-*` attributes or JSON, not by the HTML of a cell.
5. Switches which can't be used are disabled.
6. The page is never wider than the window.


## Acceptance criteria

- [x] Test: the page of a deployment with 9 objects has 9 objects in the data of the table, ordered by level, no level rows, and the stylesheet of bootstrap-table.
- [x] Test `set_objects_ready`: sets the given objects; finished objects stay unchanged; `403` without `run`; `409` for a canceled deployment; `404` and no change if an object is unknown; `422` for invalid input; one entry in the processing history.
- [x] Test: `can_change` is false for finished objects, for all objects of a canceled deployment and for users without `run` (the switches are rendered from it as `disabled`, checked in Chrome).
- [x] Manual check in headless Chrome (no [browser tests](../features/web-ui-browser-tests.md) yet): filter by type `pgm` (14 of 21 objects), `None ready` → one request, the 13 objects which aren't finished change, the others not, page 2 of the filter shows the new state, the state is the same after a reload. The switches of `o'brien` and `<img src=x onerror=...>` work.
- [x] Manual check in headless Chrome: no horizontal scrolling at 1440 px and 1024 px; the flow chart scrolls inside its box when it's wider.
- [x] Docs: [webapi.md](../webapi.md). Changelog entry.


## Decisions

* The rows come from a JSON block of the page (`objects_table` of `show_details_by_id`), rendered by `static/assets/js/deployment-objects.js` with bootstrap-table and `escape: true`. Objects are identified by these values.
* Whether a switch can be used is decided by the server (`can_change`: permission `run` for the workflow, deployment not finished or canceled, object not finished). Users without `run` don't get the buttons `All ready` / `None ready`.
* `All ready` / `None ready` are buttons in the toolbar of the table instead of the switch in the header. They apply to the objects which match the filters, on all pages.
* `set_objects_ready` changes nothing if one object is unknown (`404`). Only objects whose value changes are counted and logged; no change, no entry in the processing history.
* `Source Only` shows `yes` / `no` instead of `True` / `None`.
* Number 7 had a second cause: the content column of `base.html` (Bootstrap `.col` in a `flex-nowrap` row) got as wide as its widest content. It has `min-width: 0` now (`.app-content` in `global.css`). This also stops the sideways scrolling of the deployment list and the object list at 1024 px. `Settings` still scrolls at 1024 px (its plain tables, see [admin pages](../features/web-ui-admin-pages.md)).
* The old functions `toggleAll` and `set_source_ready_4_deployment` of the page are removed.


## Non-goals

* The new layout of the page: [deployment page](../features/web-ui-deployment-page.md). It contains these requirements; this file is the list of what has to work afterwards.


## Open questions

None. If the new deployment page isn't done soon, number 1 (one line) and 3 – 5 can be fixed in the current page.
