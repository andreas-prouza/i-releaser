# Lists: deployments, objects, start of a workflow

- **Status:** finished (2026-11-20; tested with `tests/test_lists.py`, `tests/test_web_browser_lists.py` and in headless Chrome, not on IBM i)
- **Type:** improvement
- **Priority:** P2
- **Source:** [Modernization of the web front end](web-ui-modernization.md), step 6
- **Depends on:** [Layout and styles](web-ui-layout.md), [Scripts in files](web-ui-scripts.md)


## Current situation

**Deployments (`/`)**

* The heading is `Workflows <project>`. The columns are generated from the keys of the data: `version`, `status`, `workflow`, `create_time`, `update_time`, `meta_file_id`.
* The only way to open a deployment is a click on its status, which looks like a button.
* The project is chosen with a row of coloured buttons, or in the navigation. `/project/{project}` stores the project in the session and redirects to `/`: the URL of a list can't be shared or bookmarked.
* The list doesn't show where a deployment stands (which stage is waiting or failed).
* Scripts and styles of the table come from other servers (see [bugfix](../bugfixes/web-scripts-from-third-party-servers.md)).

**Object list (`/list-objects`)**

* Columns `project`, `prod_lib`, `name`, `type`, `attribute`, `latest_create_time`, `count`.
* The query returns the 1,000 objects deployed last ([deploy_object_data.py:137](../../modules/db/deploy_object_data.py#L137)). Older objects are not in the page, so the filters don't find them. The page doesn't say so.
* The history of an object is a popup whose table is built from text (see [bugfix](../bugfixes/web-values-run-as-script.md), 2 and 4), with the column names of the database.

**Start of a workflow**

* Only on the page `Workflows`: `Start` creates a deployment at once, without a question, and opens it.
* Fields of [`create_fields`](../workflow.md#create-fields) can't be entered. They can only be set with the Web API.


## Feature

### Deployments

```
Deployments                                                      [Start workflow]
[ erp 2 ] [ test 1 ] [ arrow ]                 <- projects, with open deployments

[ Open | All ]   [status v] [workflow v] [search ...]
Version   Status       Workflow        Stage             Created              Last update
6         [failed]     deploy_2_test   DEPLOY · failed   2026-11-16 18:56:47  2026-11-16 18:56:50
5         [canceled]   deploy_2_test   –                 2026-11-16 18:56:47  2026-11-16 18:56:47
```

* `/project/{project}` shows the list of the project (no redirect). `/` shows the project used last, or the default project, as today.
* Projects as tabs, each with the number of its open deployments (not finished, not canceled).
* Columns: Version (a link to the deployment), Status (pill), Workflow, Stage (the failed, running, queued or ready stage and its status; `–` for finished and canceled deployments), Created, Last update. The id is a column which is hidden at first.
* A click on a row opens the deployment as well.
* `Open | All`: open deployments only, or all (default). Filters for status and workflow, a text search. Sorting by every column, newest first. Paging.
* No deployments: `No deployments in this project yet`.
* The stages for the column `Stage` are read with one query for the whole list.

### Objects

* Title `Objects`. Columns: Project, Production library, Name, Type, Attribute, Last deployment, Deployments (number).
* The rows are loaded page by page from the server (`GET /api/deploy_objects` with search, filters, sort, offset and limit; server-side paging of bootstrap-table), so every object can be found, not only the newest 1,000.
* `History` in each row opens the deployments of the object: Deployment (link, `erp 6`), Workflow, Status of the deployment, Status of the object, Time, Source. Rendered by the server (`GET /list-objects/history?...`).
* `/api/deploy_object_lifecycle/...` stays for other clients.

### Start of a workflow

* `Start workflow` on the deployment list (workflows of the shown project) and `Start` on the page `Workflows`, both only with the permission `start workflow`.
* A dialog: the workflow (chosen already on the page `Workflows`), one text field per path of its `create_fields` (`$.ticket` → `ticket`, `$.jira.issue` → `jira.issue`), and `Start`.
* It calls `POST /api/start_workflow/{wf_name}` with the fields and opens the new deployment. An error of the server (e.g. `422`) is shown in the dialog.


## Acceptance criteria

- [x] Test: `/project/test` shows the deployments of `test` without a redirect; `/` afterwards shows `test` too; an unknown project → the default project, as today.
- [x] Test: users only see projects and deployments of workflows they may read (existing tests still pass).
- [x] Test: the column `Stage` for a failed, a running, a queued, a ready, a finished and a canceled deployment; with parallel stages the first one.
- [x] Test: the number of open deployments per project.
- [x] Test: the list has no column name of the database and no `None`.
- [x] Test `deploy_objects`: search, filter by project and type, sort, offset and limit, the total number; an object which is not among the newest 1,000 is found; only objects of readable workflows.
- [x] Test: the history of an object with `'` and `<` in its name is shown as text; `403` / empty without `read`.
- [x] Test: `Start workflow` is only in the page of users with `start workflow` for a workflow of the project.
- [x] Browser tests (or manual checks, see [browser tests](web-ui-browser-tests.md)): filter and sort the deployments; open a deployment by its row; page through the objects and search; start a workflow with a field of `create_fields`, and the new deployment has the value in its custom data.
- [x] Measurement: the deployment list of a project with 2,000 deployments, before and after (time of the response, size of the page). Numbers in this file: 2,000 deployments, median of 10, 2026-11-20: before 28 ms and 2,044 KB, after 31 ms and 610 KB (the rows as data; two more queries for `Stage` and the numbers of the tabs).
- [x] Docs: [webapi.md](../webapi.md) (`deploy_objects`), screenshots of [README.md](../../README.md) (renewed at the end of the [modernization](web-ui-modernization.md)).


## Implementation (2026-11-20)

* Server: `modules/db/deployment_list_data.py` (open deployments per project, the stage of each deployment of a list, objects page by page, history of an object); routes `deployment_list`, `select_project` (no redirect any more), `get_deploy_objects`, `object_history`, `get_startable_workflows`.
* Deployment list: the rows are a JSON block, bootstrap-table with `escape`; `Open | All` with `filterBy`. A click on the row opens the deployment (not while text is selected).
* `Stage`: failed, else running (`in process`, preparation), else waiting for the processing service, else ready; the first stage (by id) of these. `–` for finished and canceled deployments.
* Objects: bootstrap-table with server-side paging through `app/api.js` (errors and an ended session as on the other pages). The selects of the filters get their values from the server (`project`, `type`, `attribute`). `%` and `_` in a search are characters. The old query of the newest 1,000 objects (`deploy_object_data.get_deploy_object_list`, which built SQL from the names of its filters) is removed.
* Start of a workflow: `pages/start-workflow.js`, used by the deployment list and the page `Workflows` (which shows `Start` only with the permission now). A field of `create_fields` with a position in a list (`$.a[0]`) can't be entered and is left out; empty fields are not sent.


## Non-goals

* One list over all projects
* Live updates of the list ([live updates](web-ui-live-updates.md) is for the deployment page)
* Export of the lists
* Custom data as columns of the list (it differs per workflow)


## Decisions (2026-11-19)

1. Start of a workflow in the web app: kept, with the dialog and one input field per path of `create_fields`.
2. Projects as tabs above the list.
3. The biggest project has fewer than 2,000 deployments: the deployment list is loaded at once (sorting, filters and paging in the browser). The objects are loaded page by page from the server, as described.
4. The column `Stage` is wanted.


## Open questions

None.
