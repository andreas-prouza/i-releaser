# Minor defects of the web pages

- **Status:** ready
- **Type:** bug
- **Priority:** P3
- **Found:** 2026-11-16, analysis of the web front end. "Seen" means in Chrome on a copy of the web app.

Small defects without their own file. Most of them disappear with the step of the [modernization](../features/web-ui-modernization.md) named in the last column; the others can be fixed on their own.


## Defects

| # | Defect | Where | Found by | Fixed with |
|---|---|---|---|---|
| 1 | Log page: `1.000` lines is never selected in the list (compares with `1090`). `<label for="cars">`. | [log.html:25](../../webapp/templates/admin/log.html#L25) | seen | now, or [admin pages](../features/web-ui-admin-pages.md) |
| 2 | Closing a log of the deployment history throws `ReferenceError: stage_id is not defined`. | [show-deployment.html:761](../../webapp/templates/overview/show-deployment.html#L761) | seen | now, or [deployment page](../features/web-ui-deployment-page.md) |
| 3 | User page: `Deleted!` is shown before the server has answered, also if the token was not deleted. The button to confirm is called `Yes, cancel`. | [user.html:87](../../webapp/templates/admin/user.html#L87) | code review | now, or [admin pages](../features/web-ui-admin-pages.md) |
| 4 | User page: the new API token is written to the browser console (`console.log(data)`). | [user.html:61](../../webapp/templates/admin/user.html#L61) | code review | now |
| 5 | 48 `console.log` / `console.error` lines for debugging in the templates (`Hier 1`, `Ergebnis:`, every response of the server). | `show-deployment.html` (26), `settings.html` (18), others | counted | [scripts](../features/web-ui-scripts.md) |
| 6 | Navigation: a project is never marked as active (the link sends `project_erp`, the template compares with `project-erp`, and the redirect to `/` drops the parameter). | [base.html:79](../../webapp/templates/base.html#L79), [routes.py:187](../../webapp/routes/routes.py#L187) | seen | [layout](../features/web-ui-layout.md) |
| 7 | The browser tab has no title, except on `Settings` and the error page. | all templates | seen | [layout](../features/web-ui-layout.md) |
| 8 | Login page: `Cancel`, `Forgot password?` and `Remember me` do nothing. `<h1>Login</b></h1>`. | [login.html:72](../../webapp/templates/login.html#L72) | seen | [layout](../features/web-ui-layout.md) |
| 9 | A `<form>` inside the `<form name="main">` of the base template (not allowed in HTML): login, user, workflows, log, error and deployment page. | [base.html:151](../../webapp/templates/base.html#L151) | code review | [layout](../features/web-ui-layout.md) |
| 10 | Error page: the text `A fucking error occured!`. The button to close the message does nothing (attributes of Bootstrap 3). | [error.html:21](../../webapp/templates/error.html#L21) | seen | now, or [layout](../features/web-ui-layout.md) |
| 11 | Settings: `Web port ????`. | [routes.py:290](../../webapp/routes/routes.py#L290) | seen | [admin pages](../features/web-ui-admin-pages.md) |
| 12 | Settings: after each reload the tab `General` is shown, also after a change on the tab `Permission` (new user, workflow, stage). | [settings.html:446](../../webapp/templates/admin/settings.html#L446) | code review | [permissions page](../features/web-ui-permissions-page.md) |
| 13 | Deployment page: `Projekt` (German), times with microseconds, `None` for empty values (description, remote dir, source only). | `show-deployment.html`, `stage-actions-details.html` | seen | [deployment page](../features/web-ui-deployment-page.md) |
| 14 | Steps window: wider than the screen at 1440 px, the log icons on the right are cut off. | `stage-actions-details.html` | seen | [deployment page](../features/web-ui-deployment-page.md) |
| 15 | Deployment list: the heading is `Workflows <project>`, the column names are the names of the database (`meta_file_id`, `create_time`). The buttons of the other projects are `disabled` buttons inside links (works in Chrome, not allowed in HTML). | [list-deployments.html:19](../../webapp/templates/overview/list-deployments.html#L19), [:43](../../webapp/templates/overview/list-deployments.html#L43) | seen | [lists](../features/web-ui-lists.md) |
| 16 | Dialog texts: `No, ups!`, `Your cancelation has been canceled :-)`, `droped`. A canceled dialog is followed by a second dialog. | `show-deployment.html`, `user.html` | seen | [scripts](../features/web-ui-scripts.md) |
| 17 | The connection of the auto refresh is closed for good after the first error (e.g. a restart of the web app). The page stays open and looks current. | [show-deployment.html:661](../../webapp/templates/overview/show-deployment.html#L661) | code review | [live updates](../features/web-ui-live-updates.md) |
| 18 | Workflows page: heading `Raw JSON file`, `<br\>`. | [workflows.html:29](../../webapp/templates/admin/workflows.html#L29) | seen | [admin pages](../features/web-ui-admin-pages.md) |


## Acceptance criteria

- [ ] Each defect is fixed, or gone with the page it was in.
- [ ] Tests where they are possible without a browser: 1 (selected option), 7 (title of each page), 10 (text of the error page), 11.
- [ ] No `console.log` in templates and own scripts (test).


## Non-goals

* Defects with their own file, see the [list](README.md)


## Open questions

None.
