# Admin pages: settings, logs, workflows, user

- **Status:** finished (2026-11-20; tested with `tests/test_admin_pages.py`, `tests/test_web_browser_admin.py` and in headless Chrome, not on IBM i)
- **Type:** improvement
- **Priority:** P3
- **Source:** [Modernization of the web front end](web-ui-modernization.md), step 8
- **Depends on:** [Layout and styles](web-ui-layout.md), [Scripts in files](web-ui-scripts.md)


## Current situation

**Settings → General** ([settings.html](../../webapp/templates/admin/settings.html))

* Own tab buttons and CSS instead of the tabs of Bootstrap. The tab is not part of the URL (see [minor defects](../bugfixes/minor-web-defects.md), 12).
* `Web port ????`, `Web path` (the directory of `routes.py`), the allowed users as one line of text.
* API tokens of all users and the jobs of the processing service as plain tables inside table cells. Jobs show the id of the stage, not its name.
* Every action of the processing service reloads the page.

**Logs** ([log.html](../../webapp/templates/admin/log.html))

* The last lines of a file, newest first, as one block of text. The number of lines is a list which changes the URL (see [minor defects](../bugfixes/minor-web-defects.md), 1).
* No search, no filter by level, no refresh.

**Workflows** ([workflows.html](../../webapp/templates/admin/workflows.html))

* Heading `Raw JSON file`. A table with `Start` and the name; the definition as JSON behind `Click to expand/collapse json`, highlighted by a script from another server (see [bugfix](../bugfixes/web-scripts-from-third-party-servers.md)).
* Nothing shows what a workflow does without reading the JSON.

**User** ([user.html](../../webapp/templates/admin/user.html))

* The API token (masked), its dates, a trash icon and `Renew`. See [minor defects](../bugfixes/minor-web-defects.md), 3 and 4.
* The new token is shown in a dialog as plain text, without a way to copy it and without the note that it's shown only once.


## Feature

### Settings

Called `Administration` since 2026-11-24, its tab `General` is `System`, and the tab `Security` is new (see decisions).

* Tabs with their own URL: `System` (`/settings`), `Processing` (`/settings/processing`), `Permissions` (`/settings/permissions`, see [permissions page](web-ui-permissions-page.md)), `Security` (`/settings/security`), `Audit` (`/settings/audit`, see [audit log](audit-log.md)).
* **General** (now `System`): default project, version of the app and of the database, start of the web app and of the processing service ([start times](start-times.md)), paths of the installation, as key and value list. `Web port` is removed. Data retention and notifications.
* **Security:** API tokens of the users as a table (user, name, scope, created, last used, expires, masked token, `Revoke`), the two-factor authentication (policy, users with `Reset`), the blocked logins (`Unblock`).
* **Processing:** the mode with `Change` and where the value comes from; the processing service with its status as pill, `Start`, `Stop`, `Restart` and the switch `Start automatically` with the notes of today; the jobs as a table with sorting, filters and paging: job, deployment (link), stage (name), user, status (pill), queued, started, ended, duration, process, error.
* The result of an action is a toast; the output of the service script is shown in a dialog as today. The part of the page is loaded again, the page is not reloaded.
* The functions are those of [processing settings](processing-settings-in-web-app.md) and [auto start](processing-service-auto-start.md). Nothing changes on the server.

### Logs

* `/log/{file}` with the files as tabs or a list.
* A bar: number of lines (100, 500, 1,000, 10,000), level (`all`, `WARNING` and above, `ERROR`), a text search, `Refresh`, `Download`.
* The lines in monospace, newest first, `WARNING` and `ERROR` marked by colour, long lines wrapped.
* Level and search filter the loaded lines in the browser.

### Workflows

* Title `Workflows`. One card per workflow: name, project, the stages as [stage flow](web-ui-deployment-page.md#stage-flow) without status, per stage its steps on request; marks for `parallel`, `editable_fields`, `create_fields`, hooks.
* `Start` (with the permission `start workflow`) opens the dialog of [lists](web-ui-lists.md#start-of-a-workflow).
* `JSON` shows the definition, highlighted by the local Prism, with a copy button.
* Invalid workflow files stay as a message on top, for users with `admin`.

### User

* Title `My account`: the user, the roles, and the permissions the user has in the end (read only).
* **API tokens** (since 2026-11 several, [API v2](api-v2.md#decisions-2026-11-24)): name, scope, masked token, created, last used, expires.
  * `New token`: a dialog with name, scope and days until it expires. The new token is shown once, with `Copy` and the note that it can't be shown again.
  * `Delete` of a token: asks. `Deleted` is shown after the server has confirmed it.
* The token is not written to the console.


## Acceptance criteria

- [x] Test: `/settings`, `/settings/processing` and `/log/{file}` need `admin` (`403` otherwise), each has its title and active entry.
- [x] Test: the settings don't contain `????`; the jobs show the name of the stage and a duration.
- [x] Test: the log page with 1,000 lines has `1,000` selected; a level filter value in the URL is kept.
- [x] Test: the workflows page shows only readable workflows, `Start` only with `start workflow`, the invalid files only with `admin` (existing tests still pass).
- [x] Test: the user page lists the roles and the effective permissions.
- [x] Test: no page loads anything from another server.
- [x] Browser tests (or manual checks, see [browser tests](web-ui-browser-tests.md)): change the processing mode and start the service without a reload of the page; filter a log by level and text; generate a token, copy it, and use it for a request; delete it.
- [x] Docs: [processing-service.md](../processing-service.md), [permissions.md](../permissions.md#api-tokens), screenshots of [README.md](../../README.md) (renewed at the end of the [modernization](web-ui-modernization.md)).


## Implementation (2026-11-20)

* `web_modules/admin_view.py` prepares the data of the pages; templates `admin/settings.html`, `admin/processing.html`, `admin/log.html`, `admin/workflows.html`, `admin/user.html`, the tabs `admin/settings-tabs.html` (General, Processing, Permissions). Scripts `pages/processing.js`, `pages/log.js`, `pages/user.js`, `pages/start-workflow.js`.
* No template is in `LEGACY_TEMPLATES` any more: all pages follow the [rules](web-ui-scripts.md#rules). `web.deploy.js` isn't loaded by any page; it stays for custom templates until [step 9](web-ui-security-headers.md).
* Processing: after an action the part `data-part="processing"` is loaded again. The jobs (the newest 50) with the name of the stage, the deployment (`erp 6`) and the duration, from one query.
* Logs: a line without level (e.g. of a traceback) gets the level of the line before it. `Download` sends the whole file (`/log/{file}/download`), read at once, as the log grows while it's sent. Unknown values of `number_of_lines` and `level` in the URL fall back to 100 and `all`.
* Workflows: the flow of `stage_flow.py` without status (`static`), marks for parallel steps and stages, parallel deployments, editable and create fields, hooks; the steps of the stages and the JSON on request. `Start` only for workflows the user may start.
* `My account`: the roles, the permissions as chips (grey: from a role or a higher level, see [permissions page](web-ui-permissions-page.md)), the API token with `Copy` in the dialog of a new token.


## Non-goals

* More settings in the web app (see [processing settings](processing-settings-in-web-app.md))
* Editing workflow files in the web app
* Following a log live
* Deleting the tokens of other users


## Decisions (2026-11-19)

1. Workflows: the stages as flow in each card (the layout of the [deployment page](web-ui-deployment-page.md#stage-flow), without status).
2. Logs: the filter in the browser is enough (at most 10,000 loaded lines).


## Decisions (2026-11-24)

1. `Settings` is renamed to `Administration`, its tab `General` to `System`. Most of it can't be changed there: it shows the state (version, start times, service, jobs, audit) or is an action of an admin (revoke a token, unblock a login, remove old deployments). The settings themselves are mostly in `etc/settings.py`. The name matches the permission `admin` which the pages need, and the code (`templates/admin/`, `admin_view.py`).
2. The addresses stay `/settings/...` (bookmarks, links in the docs and of other tools), and so do the internal names (`data-nav="settings"`, the block `nav_active` of own pages).
3. A tab `Security` (`templates/admin/security.html`, `pages/security.js`, `admin_view.get_security`) with the API tokens, the two-factor authentication and the blocked logins: who can log in and how. `System` keeps the state of the installation, data retention and notifications. The audit log stays a tab of its own: it records more than security events (actions on deployments, viewed logs, settings), and it's a large table with filters and a CSV export.
4. `Permissions` is no longer an entry of the navigation, only a tab: two entries opened the same page, and the navigation marked `Permissions` instead of `Administration` while the tabs of the administration were shown (like `Audit`, which never had an entry). The page keeps its title `Permissions` with the breadcrumb, as its header shows when the last change has been saved.


## Open questions

None.
