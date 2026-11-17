# Deployment page: defects of the table "Objects to deploy"

- **Status:** ready
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

- [ ] Test: the page of a deployment with 9 objects contains 9 rows in the table, no level rows, and the stylesheet of bootstrap-table.
- [ ] Test `set_objects_ready`: sets the given objects; finished objects stay unchanged; `403` without `run`; `409` for a finished deployment; one entry in the processing history.
- [ ] Test: switches of finished objects, and all switches of a finished deployment, are `disabled`.
- [ ] Browser test (or manual check, see [browser tests](../features/web-ui-browser-tests.md)): filter by type, "all ready" → only the filtered objects change, one request, no error dialog; an object `o'brien` is changed too.
- [ ] Browser test (or manual check): no horizontal scrolling at 1440 px and 1024 px.
- [ ] Docs: [webapi.md](../webapi.md). Changelog entry.


## Non-goals

* The new layout of the page: [deployment page](../features/web-ui-deployment-page.md). It contains these requirements; this file is the list of what has to work afterwards.


## Open questions

None. If the new deployment page isn't done soon, number 1 (one line) and 3 – 5 can be fixed in the current page.
