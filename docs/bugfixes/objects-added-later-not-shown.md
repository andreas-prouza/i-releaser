# Deployment page: objects added while the page is open are not shown

- **Status:** ready (implemented 2026-11-27; checked in Edge with the real template section and scripts and a mocked `/api/deployment_objects`. The new tests in `tests/test_web_pages.py` and `tests/test_web_browser_live.py` haven't run yet: the test web app needs Linux, not checked on IBM i)
- **Type:** bug (regression of the [live updates](../features/web-ui-live-updates.md), 4.1.0)
- **Priority:** P2
- **Found:** 2026-11-27, after the update of an installation to 4.1.1: the rollback workflow of a custom installation showed no objects although its deployment had 7 (in the database, restored)


## Current situation (before)

Some deployments get their objects only after they are created, e.g. a workflow whose `SCRIPT` step copies the objects of another deployment (`Meta_File.add_deploy_object`). The deployment page is open from the start.

1. With no objects, [show-deployment.html](../../webapp/templates/overview/show-deployment.html) rendered only `This deployment has no objects`, without the table `#object_list`.
2. `init_objects` in [deployment-objects.js](../../webapp/static/assets/js/pages/deployment-objects.js) then returned `null`.
3. When the objects were added, the live updates saw the change of `parts.objects`, but `refresh_objects` in [deployment.js](../../webapp/static/assets/js/pages/deployment.js) returned at once (`objects` is `null`).

The page showed no objects until it was loaded again. Before 4.1.0 a change loaded the whole page again, so the objects were shown.


## Requirements

1. Objects added while the page is open are shown with the next live update, without loading the page again.
2. Without objects the page shows `This deployment has no objects`. When the last object is removed, it shows that again.
3. Sorting, filters and the page of the table stay as before (see [live updates](../features/web-ui-live-updates.md)).


## Acceptance criteria

- [x] Manual check in Edge (Playwright, the section of the template and the scripts of the web app, `/api/deployment_objects` mocked): without objects the message is shown and the table hidden; after a refresh with 12 objects the table, its header, filters and toolbar are shown, 10 rows on page 1, 2 on page 2; after a refresh with 0 objects the message again; with 7 objects at the start as before; no script errors.
- [ ] Test `test_objects_table_without_objects`: the page without objects has the message and the hidden table.
- [ ] Browser test `test_objects_added_later_are_shown`: objects added to the database while the page is open are shown with their number, without loading the page again.
- [x] Changelog entry.


## Decisions

* The table is always rendered, hidden without objects (`data-objects-table`); the message is a second element (`data-objects-empty`). `init_objects` sets up bootstrap-table also without rows, its `refresh` shows the one or the other.
* bootstrap-table set up in a hidden element gets `resetView` when it's shown the first time, so the header gets its width.
* The alternative, `location.reload()` when objects arrive, was not chosen: it would lose what the user does on the page (see [live updates](../features/web-ui-live-updates.md)).


## Open questions

None.
