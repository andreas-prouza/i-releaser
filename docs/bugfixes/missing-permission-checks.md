# Missing permission checks

- **Status:** finished
- **Type:** security
- **Priority:** P1
- **Found:** 2026-10-23, code review
- **Confidential:** don't publish before the fix is released


## Current situation

These endpoints only require a login. They don't check the permissions of the workflow:

| Endpoint | Code | What any user can do |
|---|---|---|
| `POST /api/set_source_ready_4_deployment/{meta_file_id}` | [routes.py:656](../../webapp/routes/routes.py#L656) | Include or exclude objects of any deployment |
| `GET /api/get_action_log/{id}` | [routes.py:344](../../webapp/routes/routes.py#L344) | Read stdout/stderr of any step (by id) |
| `GET /api/get_activity_log/{id}` | [routes.py:331](../../webapp/routes/routes.py#L331) | Read the log of any stage run (by id) |
| `GET /api/show_processing_history/{meta_file_id}` | [routes.py:357](../../webapp/routes/routes.py#L357) | Read who did what in any deployment |
| `/` (list of deployments) | [routes.py:45](../../webapp/routes/routes.py#L45) | See all deployments of any project |
| `GET /api/list_deployments/{project}` | [routes.py:107](../../webapp/routes/routes.py#L107) | Same as JSON, incl. custom data |
| `GET /api/get_projects` | [routes.py:768](../../webapp/routes/routes.py#L768) | Number of deployments per project and status |
| `/list-objects`, `GET /api/deploy_object_lifecycle/...` | [routes.py:78](../../webapp/routes/routes.py#L78), [routes.py:95](../../webapp/routes/routes.py#L95) | All objects of all deployments |
| `/workflows`, `GET /api/get_workflows` | [routes.py:197](../../webapp/routes/routes.py#L197), [routes.py:760](../../webapp/routes/routes.py#L760) | All workflow definitions (commands, hosts, paths) |
| `/log/{log}` | [routes.py:129](../../webapp/routes/routes.py#L129) | See [session takeover via logs](session-takeover-via-logs.md) |

Permission errors are returned with status 500 instead of 403.


## Requirements

1. Each endpoint which reads or changes data of a deployment checks the permission for the workflow of that deployment:
   * reading (logs, history, objects): `read`;
   * including or excluding objects: see open questions.
2. Lists (`/`, `list_deployments`, `get_projects`, `list-objects`, `deploy_object_lifecycle`) only contain deployments of workflows the user may `read`.
3. Workflow definitions: see open questions.
4. A missing permission is answered with 403 (see [API consistency](../features/api-consistency.md)).
5. Custom routes: `docs/scripts.md` shows how to check permissions (already documented).


## Acceptance criteria

- [x] Test matrix: a user without `read` on workflow X gets 403 for each endpoint above with a deployment of X, and doesn't see X's deployments in the lists.
- [x] Test: a user with `read` on X gets the same data as today.
- [x] Test: including/excluding an object without the required permission → 403, object unchanged.


## Non-goals

* New permission levels beyond what the open questions decide


## Decisions

* Permission for including/excluding objects? **`run` on general or workflow level.**
* Who sees workflow definitions? **Users with `read` on that workflow.**
