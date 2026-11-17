# Lists: deployments, objects, start of a workflow

- **Status:** draft
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

- [ ] Test: `/project/test` shows the deployments of `test` without a redirect; `/` afterwards shows `test` too; an unknown project → the default project, as today.
- [ ] Test: users only see projects and deployments of workflows they may read (existing tests still pass).
- [ ] Test: the column `Stage` for a failed, a running, a queued, a ready, a finished and a canceled deployment; with parallel stages the first one.
- [ ] Test: the number of open deployments per project.
- [ ] Test: the list has no column name of the database and no `None`.
- [ ] Test `deploy_objects`: search, filter by project and type, sort, offset and limit, the total number; an object which is not among the newest 1,000 is found; only objects of readable workflows.
- [ ] Test: the history of an object with `'` and `<` in its name is shown as text; `403` / empty without `read`.
- [ ] Test: `Start workflow` is only in the page of users with `start workflow` for a workflow of the project.
- [ ] Browser tests (or manual checks, see [browser tests](web-ui-browser-tests.md)): filter and sort the deployments; open a deployment by its row; page through the objects and search; start a workflow with a field of `create_fields`, and the new deployment has the value in its custom data.
- [ ] Measurement: the deployment list of a project with 2,000 deployments, before and after (time of the response, size of the page). Numbers in this file.
- [ ] Docs: [webapi.md](../webapi.md) (`deploy_objects`), screenshots of [README.md](../../README.md).


## Non-goals

* One list over all projects
* Live updates of the list ([live updates](web-ui-live-updates.md) is for the deployment page)
* Export of the lists
* Custom data as columns of the list (it differs per workflow)


## Open questions

1. Start of a workflow in the web app: is it used, or are deployments always created by the OBI extension or the Web API (with commit and object list)? Proposal: keep `Start`, with the dialog as confirmation. Are the input fields for `create_fields` wanted?
2. Projects as tabs above the list (**recommended**), or one list of all projects with a filter?
3. How many deployments per project and how many different objects exist in your installation? With many thousands of deployments the list should load its rows page by page too (as the objects).
4. Is the column `Stage` wanted?
