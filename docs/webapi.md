# Web API

* [Authentication](#authentication)
* [Responses and errors](#responses-and-errors)
* [Example: create a deployment and run a stage](#example-create-a-deployment-and-run-a-stage)
* [Endpoints (v2)](#endpoints)
  * [Deployments](#deployments)
  * [Stages and steps](#stages-and-steps)
  * [API tokens](#api-tokens)
  * [Other endpoints](#other-endpoints)
  * [Processing service](#processing-service), [notifications](#notifications), [health check](#health-check), [users and permissions](#users-and-permissions)
* [Details](#details)
* [Appendix: Web API v1 (deprecated)](#appendix-web-api-v1-deprecated)

All actions of the web app are available as HTTP endpoints. They use the same [permissions](permissions.md) as the web app.
The **Web API v2** (`/api/v2/...`) is the API for other applications ([feature](features/api-v2.md)). `/docs` shows its OpenAPI description (`/openapi.json`); try it there after the login.
The **Web API v1** (`/api/run_stage/...`, ...) still works the same, but its answers have the header `Deprecation: true`: it's removed in the next major version. See the [appendix](#appendix-web-api-v1-deprecated) for the old paths and the new ones.

A deployment is identified by its internal `id` (`general.id` in its JSON), not by its version.
Stage ids are in `general.open_stages[].id` and `general.processed_stages[].id`, step ids in `actions[].id` of a stage.
`waiting_for` of a stage lists the stages of its `after_stages_finished` which are not finished yet: the stage stays `new` until it's empty (see [parallel branches](concepts.md#parallel-branches)).


## Authentication

Two ways:

* **API token** (for other applications): create a token on the user page of the web app (`My account`, `/user`) and send it in the header `Authorization`:

  ```
  Authorization: Bearer irt_4f9c...e1
  ```

  The request runs with the permissions of the user who owns the token. A user can have several tokens (one per client), each with a name, a scope and an expiry, see [API tokens](permissions.md#api-tokens):
  * Scope `write`: all actions the user may do. Scope `read`: only `GET` requests (`403` for others, also of v1). Except the two reads of v1 which are sent with `POST`: `get_meta_file_json` and `list_deployments` (the OBI extension reads a deployment with `POST`).
  * An expired token: `401` with the message `Your API token has expired ...`.
  * The query parameter `?auth-token=...` still works, but it's deprecated: URLs end up in the logs of proxies.

* **Session** (the web app): log in with a form post of `user`, `password` and, with [two-factor authentication](permissions.md#two-factor-authentication), `code` to `/login` (only there). The session cookie `session_id` is valid for one hour after the last request.
  Requests with a session have to come from the web app itself: requests which change data need an `Origin` (or `Referer`) header of the own host.

Use HTTPS.

Without a valid login `/api/...` answers with status 401:

```json
{"status": "error", "message": "You are not logged in"}
```


## Responses and errors

Responses are JSON. Web API v2:

* A request for a resource answers the resource itself, e.g. the deployment. A list answers `{"items": [...], "next_cursor": "..."}`.
* Lists of deployments come page by page: `?limit=50` (1 to 500, default 50); the next page with `?cursor=` and the `next_cursor` of the page before. `next_cursor` is `null` on the last page.
* `201`: created (the answer is the new resource), `202`: accepted (a stage runs in the background), `204`: deleted (no content).
* Unknown fields in a body are refused (`422`), so a typo isn't ignored.

Actions of v1 return `{"status": "success", ...}`.

All errors have the same format (v1 and v2, also for unknown paths and wrong methods):

```json
{"status": "error", "message": "User anna does not have permission 'run' (workflow: erp_release, stage: PROD)"}
```

| Status | Meaning |
|---|---|
| 401 | Not logged in, or invalid token |
| 403 | Missing permission, a token with the scope `read` for a change, or a request with a session from another origin. With `"step_up": true`: the action needs a recent code of the two-factor authentication (`POST /api/mfa/verify`, then send the request again) |
| 404 | Deployment, stage, step, job or path not found |
| 405 | Wrong method (e.g. `GET` of an action) |
| 409 | Not possible in the current status, e.g. the stage isn't ready or the commit is already used |
| 422 | Invalid input |
| 502 | Another server refused or didn't answer (e.g. the mail server of a test message) |
| 500 | Unexpected error. The message contains an error id to find the details in the log. |

Pages of the web app (`/show_details/...`, ...) answer errors and a missing login with an HTML page. With the header `X-Requested-With: fetch` they answer with JSON as above (the scripts of the pages send it, see `static/assets/js/app/api.js`).


## Example: create a deployment and run a stage

```bash
URL=https://ireleaser.example.com
TOKEN=irt_4f9c...e1

# Create a deployment of workflow erp_release with custom data
curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"workflow": "erp_release", "custom_data": {"ticket": "ABC-1"}}' \
     "$URL/api/v2/deployments"
# 201 {"general": {"id": 123, "deploy_version": 42,
#   "open_stages": [{"id": 456, "name": "START", "status": "ready", ...}, ...], ...}, ...}

# Run stage START (id 456) of deployment 123
curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{}' \
     "$URL/api/v2/deployments/123/stages/456/runs"
# 202 {"mode": "thread"}

# Follow its status
curl -s -H "Authorization: Bearer $TOKEN" "$URL/api/v2/deployments/123"
```


## Endpoints

Web API v2. Permission "login" means: any logged-in user, no further permission is checked.
Lists only contain what the user may read.

### Deployments

| Method | Path | Permission | Description |
|---|---|---|---|
| `GET` | `/api/v2/projects` | `read` | Projects with the number of their deployments per status: `{"items": [{"name": "erp", "deployments": {"finished": 40, "ready": 1}}]}` |
| `GET` | `/api/v2/workflows` | `read` | Workflow definitions |
| `GET` | `/api/v2/deployments?project=&status=&limit=&cursor=` | `read` | Deployments, newest first, page by page: `id`, `project`, `version`, `workflow`, `status`, `commit`, `create_time`, `update_time` |
| `POST` | `/api/v2/deployments` | `start workflow` | Create a deployment. [Details](#create-a-deployment) |
| `GET` | `/api/v2/deployments/{id}` | `read` | The complete deployment: general data, stages with their steps, objects, history, custom data |
| `POST` | `/api/v2/deployments/{id}/cancel` | `cancel workflow` | Set the deployment to `canceled` and remove its stages from the queue of the processing service. A finished deployment: `409`. Answer: the deployment |
| `POST` | `/api/v2/deployments/{id}/reset` | `run` | Set hanging stages back to `ready`. The deployment gets the status which follows from its stages. Answer: the deployment |
| `PATCH` | `/api/v2/deployments/{id}/custom-data` | `edit-custom-data` | Change editable fields: `{"fields": {"$.ticket": "ABC-2"}}`. Answer: `{"changed": ["$.ticket"], "custom_data": {...}}`. [Details](#edit-custom-data) |
| `PATCH` | `/api/v2/deployments/{id}/objects` | `run` | Include or exclude objects: `{"objects": [{"lib": "devlib", "name": "orders", "type": "file"}], "ready": true}`. Finished objects stay unchanged; the answer lists them: `{"changed": 12, "finished": [...]}`. An unknown object: `404`, nothing is changed |
| `GET` | `/api/v2/deployments/{id}/history` | `read` | Who did what and when, oldest first |
| `GET` | `/api/v2/deployments/{id}/jobs` | `read` | The runs of its stages by the [processing service](processing-service.md) |

### Stages and steps

| Method | Path | Permission | Description |
|---|---|---|---|
| `POST` | `/api/v2/deployments/{id}/stages/{stage_id}/runs` | `run` | Run a stage in the background, now or at a [scheduled time](processing-service.md#scheduled-runs). `202`. [Details](#run-a-stage) |
| `POST` | `/api/v2/deployments/{id}/stages/{stage_id}/reset` | `run` | `{"kind": "hanging"}`: a stage which hangs in `in process` goes back to `ready` (one minute after its last change, not while it's in the processing service). `{"kind": "last-finished"}`: the last finished stage goes back to `ready` (see [workflow](workflow.md#reset-the-last-finished-stage)). Answer: `{"id", "name", "status"}` |
| `POST` | `/api/v2/deployments/{id}/stages/{stage_id}/approvals` | `4-eyes check` (stage) | Approve a stage with `four_eyes_check` ([four-eyes check](permissions.md#four-eyes-check)): `201 {"approved_by", "time"}`. Not the creator of the deployment (`409`). Step-up |
| `PATCH` | `/api/v2/deployments/{id}/steps/{step_id}` | `change check error` | `{"check_error": false}`: whether a failure of the step stops the stage. Not possible for finished stages or deployments |
| `GET` | `/api/v2/deployments/{id}/steps/{step_id}/log` | `read` | The runs of a step: `{"items": [{"id", "status", "stdout", "stderr", "create_time"}]}` |
| `DELETE` | `/api/v2/jobs/{job_id}` | `run` | Remove a stage from the queue of the [processing service](processing-service.md), as long as it hasn't started. Also cancels a scheduled run. `204`, `409` once it has started |

### API tokens

Only in the web app (with the session): a token can't create, see or delete tokens.

| Method | Path | Permission | Description |
|---|---|---|---|
| `GET` | `/api/v2/tokens` | login | The own tokens: `id`, `name`, `scope`, `masked` (the end of the token), `created_at`, `expires_at`, `last_used_at`, `legacy` |
| `POST` | `/api/v2/tokens` | login | `{"name": "OBI extension", "scope": "write", "expires_in_days": 365}` (`scope` and `expires_in_days` optional; at most `C_TOKEN_MAX_DAYS`): `201` with the `token`, which is shown only this once. Names are unique per user (`409`), at most 20 tokens. Step-up |
| `DELETE` | `/api/v2/tokens/{token_id}` | login; `admin` for the token of another user | `204`. The token of another user: step-up, `404` for users without `admin` |

### Other endpoints

Not part of v2 (yet): they keep their paths and aren't deprecated.

| Method | Path | Permission | Description |
|---|---|---|---|
| `GET` | `/api/deployment_objects/{meta_file_id}` | `read` | The objects of a deployment as rows of the table of the deployment page: `{"meta_file_id": 6, "can_change": true, "objects": [{"id", "ready", "level", "prod_lib", "lib", "name", "type", "attribute", "source_only", "status", "status_view", "can_change"}]}` |
| `GET` | `/api/deploy_objects` | `read` (only objects of readable workflows) | The object list, one row per object, page by page: `?search=&filter={"project": "erp", "type": "pgm"}&sort=name&order=asc&offset=0&limit=25` → `{"total": 1101, "rows": [{"project", "prod_lib", "name", "type", "attribute", "last_deployment", "deployments"}]}`. Filters: `project`, `type`, `attribute` (value), `prod_lib`, `name` (part); at most 500 rows |
| `GET` | `/api/deploy_object_lifecycle/{project}/{prod_lib}/{name}/{type}/{attribute}` | `read` | All deployments of an object |
| `GET` | `/api/get_activity_log/{id}` | `read` | Log of one run of a stage (`run_history[].id` of the deployment) |
| `GET` | `/api/watch_state/{meta_file_id}` | `read` | Server-sent events with hashes of the deployment's state whenever it changes: `page` (the deployment, its stages, jobs, objects and runs), `stages` (one per stage, with its steps, by stage id) and `parts` (`header`, `flow`, `objects`, `activity`: the parts of the deployment page). Used by the web app for its live updates and by the OBI extension |
| `GET` | `/show_details/{meta_file_id}/stage/{stage_id}` | `read` | HTML of the steps of a stage, a part of the deployment page (used by the web app) |
| `GET` | `/list-objects/history?project=&prod_lib=&name=&type=&attribute=` | `read` | HTML of the deployments of an object, a part of the object list (used by the web app) |

### Processing service

| Method | Path | Permission | Description |
|---|---|---|---|
| `POST` | `/api/set_processing_mode/{mode}` | `admin` | `thread` or `service` for the next stages, see [processing service](processing-service.md#set-up). `409` while stages wait in the queue and `mode` is `thread`. |
| `POST` | `/api/processing_service/{action}` | `admin` | `start`, `stop` or `restart` the processing service: `{"output": "...", "service_running": true}` |
| `POST` | `/api/set_service_auto_start/{enabled}` | `admin` | `true` or `false`: [start the processing service automatically](processing-service.md#start-automatically): `{"auto_start": true, "auto_start_paused": false}` |

### Notifications

| Method | Path | Permission | Description |
|---|---|---|---|
| `POST` | `/api/notifications/test/{channel}` | `admin` | Send a test message with a channel of `etc/notifications.json` now, see [notifications](features/notifications.md). E-mail: `{"recipient": "anna@example.com"}` (default: the `mail` of the logged-in user). `{"sent_to": "..."}`; `409` for an unknown channel or without an address, `502` if the server refused it |

### Health check

| Method | Path | Permission | Description |
|---|---|---|---|
| `GET` | `/healthz` | none | `200 {"status": "ok", "checks": {"database": "ok", "processing_service": "ok", "disk_space": "ok"}}`, `503` with `"status": "error"` if a check fails. With a login or a token also `version` and `details` (the reasons) |

### Users and permissions

| Method | Path | Permission | Description |
|---|---|---|---|
| `POST` | `/api/unblock_login/{user}` | `admin` | End the block of a user after failed logins. Step-up |
| `POST` | `/api/mfa/setup` | login, session only | Start the setup of the two-factor authentication: `{"secret", "uri", "qr_code"}` |
| `POST` | `/api/mfa/enable` | login, session only | `{"code": "123456"}`: activate it with a code of the app: `{"recovery_codes": [...]}` (shown once) |
| `POST` | `/api/mfa/disable` | login, session only | `{"code": "..."}`: turn it off (not if the policy requires it: `409`) |
| `POST` | `/api/mfa/recovery_codes` | login, session only | New recovery codes. Step-up |
| `POST` | `/api/mfa/verify` | login, session only | `{"code": "..."}`: confirm the code for actions which need a recent one (step-up) |
| `POST` | `/api/mfa/reset/{user}` | `admin` | Remove the two-factor authentication of a user (lost phone). Step-up |
| `GET` | `/api/permissions` | `admin` | Users, roles, their permissions, the workflows and the `version` of the permissions (used by the permissions page) |
| `POST` | `/api/add_permission` | `admin` | Add a user or role: `{"type": "user"\|"role", "name": "anna", "general": ["read"], "version": "..."}`. Names: not empty, no control characters, at most 64 characters, unique (`422`, `409`) |
| `POST` | `/api/save_permissions` | `admin` | Replace the permissions of the given users and roles (`{"user_permissions": {...}, "role_permissions": {...}}`, like `etc/user_permissions.json`, with `detailed_infos` for description and mail). Users and roles which are not given stay unchanged. To delete some: `"deleted_users": ["anna"]`, `"deleted_roles": ["developer"]`. Unknown users or roles: `422` (add them with `add_permission`). Nothing is changed if afterwards no user would have `admin` (`409`). |

Changes of permissions and of the processing settings need a recent code of the two-factor authentication (step-up, see [errors](#responses-and-errors)) for users who have set it up.

`version` (optional, from `/api/permissions` or the answer of the last change): the change is only made if the permissions haven't changed since, otherwise `409`. The answer contains the new `version`.



## Details

### Create a deployment

`POST /api/v2/deployments` (v1: `start_workflow`, `create_deployment`, see the [appendix](#create-a-deployment-v1)):

```json
{
  "workflow": "erp_release",
  "custom_data": {"ticket": "ABC-1", "jira": {"ticket": "ABC-1"}},
  "compiles": [{"level": 0, "sources": ["..."]}],
  "commit": "9f2c1e7",
  "object_list": "/home/build/erp/object-list.txt"
}
```

Only `workflow` is needed. The deployment:

1. gets the next version number of the workflow's project;
2. gets its stages, `START` is `ready`;
3. calls the hook `deployment_created`;
4. is the answer (`201`).

| Field | |
|---|---|
| `workflow` | Name of the workflow (not case sensitive) |
| `custom_data` | Any JSON. The fields can be limited with [`create_fields`](workflow.md#create-fields) of the workflow. Other fields, or more than 64 KB: `422` |
| `compiles` | The **compile list** of the deployment (e.g. of an OBI build list), stored in `compile-list.json` in the meta directory, not in the custom data. A list of up to `C_MAX_COMPILE_LIST_SIZE` (32 MB). `create_fields` doesn't have to list it. Scripts read it with [`meta_file.get_compile_list()`](scripts.md#compile-list) |
| `commit` | A commit hash. `409` if another deployment of the project uses the same commit and isn't canceled. Stored as `general.commit` and used by the build scripts |
| `object_list` | Path of an [object list](workflow.md#object-list) on the i-Releaser server, imported by the step `load_object_list`. It has to be in an allowed directory, otherwise `422` |

### Run a stage

`POST /api/v2/deployments/{id}/stages/{stage_id}/runs`, body (all optional):

```json
{"mode": "continue", "step": null, "run_at": "2026-11-24T22:00:00+01:00"}
```

| Field | |
|---|---|
| `mode` | `continue` (default): if the last run of this stage failed, continue with the step which isn't finished. `all`: run all steps of the stage again |
| `step` | Only this processing step of the stage |
| `run_at` | Run it later ([scheduled run](processing-service.md#scheduled-runs), only in mode `service`). ISO 8601 with time zone offset (or `Z` for UTC). Without offset, not a time, or not in the future: `422`. In mode `thread`: `409` |

The stage is run in the background. The answer (`202`) tells how:

```json
{"mode": "thread|service", "job_id": 4711, "service_running": true, "run_at": "2026-11-24T21:00:00+00:00"}
```

`job_id`, `service_running` and `run_at` are only returned in mode `service` (see [processing service](processing-service.md)).
`run_at` is the scheduled time in UTC, `null` for a run as soon as possible.
If `service_running` is `false`, the stage stays in the queue until the service has been started.
To cancel a scheduled run before its time: `DELETE /api/v2/jobs/{job_id}` (`409` once it has started).
The queued and running jobs of a deployment, with their `run_at`, are in `processing_jobs` of the deployment and in `/jobs`.

Only stages with status `ready` or `failed` can be run, otherwise `409` and nothing changes.
Without `parallel_deployment_execution_allowed`, that's also the case while another stage of the deployment (or an older deployment of the project) is running or ready.
Follow the progress with `GET /api/v2/deployments/{id}`.

### Edit custom data

`PATCH /api/v2/deployments/{id}/custom-data`

```json
{"fields": {"$.ticket": "ABC-2", "$.approval.by": "anna"}}
```

Only the paths in `editable_fields` of the workflow can be changed (see [editable custom fields](workflow.md#editable-custom-fields)), others: `422`.
Calls the hook `custom_data_changed`. An approval of the [four-eyes check](permissions.md#four-eyes-check) becomes invalid.


## Appendix: Web API v1 (deprecated)

The paths before v2. They work as before, use the same checks (the same functions, `modules/application/`), and answer with the header `Deprecation: true`. They are removed in the next major version: change your clients to v2.
Actions which change data are shown with `POST`. With an API token they also work with `GET`, but that's deprecated too.

| v1 | v2 |
|---|---|
| `GET /api/get_projects` | `GET /api/v2/projects` |
| `GET /api/get_workflows` | `GET /api/v2/workflows` |
| `GET /api/list_deployments/{project}` | `GET /api/v2/deployments?project={project}` (page by page) |
| `POST /api/start_workflow/{wf_name}` (body: custom data and `compiles`) | `POST /api/v2/deployments` with `workflow`, `custom_data`, `compiles` |
| `POST /api/create_deployment/{wf_name}/{commit}/{obj_list}` | `POST /api/v2/deployments` with `workflow`, `commit`, `object_list` |
| `POST /api/get_meta_file_json/{meta_file_id}` | `GET /api/v2/deployments/{id}` |
| `POST /api/cancel_deployment/{meta_file_id}` | `POST /api/v2/deployments/{id}/cancel` |
| `POST /api/reset_deployment_status/{meta_file_id}` | `POST /api/v2/deployments/{id}/reset` |
| `POST /api/edit_custom_data/{meta_file_id}` | `PATCH /api/v2/deployments/{id}/custom-data` |
| `POST /api/set_source_ready_4_deployment/{meta_file_id}`, `POST /api/set_objects_ready/{meta_file_id}` | `PATCH /api/v2/deployments/{id}/objects` |
| `GET /api/show_processing_history/{meta_file_id}` | `GET /api/v2/deployments/{id}/history` |
| `POST /api/run_stage/{meta_file_id}/{stage_id}/{option}` (`continue`, `run_all`) | `POST /api/v2/deployments/{id}/stages/{stage_id}/runs` with `mode` (`continue`, `all`) |
| `POST /api/reset_stage_status/{meta_file_id}/{stage_id}` | `POST /api/v2/deployments/{id}/stages/{stage_id}/reset` with `{"kind": "hanging"}` |
| `POST /api/reset_last_finished_stage/{meta_file_id}/{stage_id}` | `POST /api/v2/deployments/{id}/stages/{stage_id}/reset` with `{"kind": "last-finished"}` |
| `POST /api/approve_stage/{meta_file_id}/{stage_id}` | `POST /api/v2/deployments/{id}/stages/{stage_id}/approvals` |
| `POST /api/set_check_error/{meta_file_id}/{stage_id}/{action_id}/{checked}` | `PATCH /api/v2/deployments/{id}/steps/{step_id}` |
| `GET /api/get_action_log/{id}` (one run) | `GET /api/v2/deployments/{id}/steps/{step_id}/log` (all runs of the step) |
| `POST /api/cancel_job/{job_id}` | `DELETE /api/v2/jobs/{job_id}` |
| `POST /api/generate_user_key` (replaces the token named `API token`) | `POST /api/v2/tokens` |
| `POST /api/drop_key` (deletes the token named `API token`) | `DELETE /api/v2/tokens/{token_id}` |
| `POST /api/revoke_token/{user}` (all tokens of the user) | `DELETE /api/v2/tokens/{token_id}` |
| `GET /api/get_stage_steps_html/{meta_file_id}/{stage_id}` | `GET /show_details/{meta_file_id}/stage/{stage_id}` (HTML) |

### Deployments (v1)

| Method | Path | Permission | Description |
|---|---|---|---|
| `POST` | `/api/start_workflow/{wf_name}` | `start workflow` | Create a deployment. The JSON body is its custom data. [Details](#create-a-deployment) |
| `POST` | `/api/create_deployment/{wf_name}`<br>`/api/create_deployment/{wf_name}/{commit}`<br>`/api/create_deployment/{wf_name}/{commit}/{obj_list}` | `start workflow` | Create a deployment with a commit and an object list. [Details](#create-a-deployment) |
| `POST` | `/api/get_meta_file_json/{meta_file_id}` | `read` | The complete deployment: general data, stages with their steps, objects, history, custom data |
| `GET` | `/api/list_deployments/{project}` | `read` | Deployments of a project, newest first: `meta_file_id`, `version`, `status`, `workflow_name`, `commit`, `create_time`, `update_time` |
| `GET` | `/api/get_projects` | `read` | Number of deployments per project and status: `{"erp": {"finished": 40, "ready": 1}}` |
| `GET` | `/api/get_workflows` | `read` | Workflow definitions |
| `POST` | `/api/edit_custom_data/{meta_file_id}` | `edit-custom-data` | Change editable fields of the custom data. [Details](#edit_custom_data) |
| `POST` | `/api/cancel_deployment/{meta_file_id}` | `cancel workflow` | Set the deployment to `canceled` and remove its stages from the queue of the processing service |
| `POST` | `/api/reset_deployment_status/{meta_file_id}` | `run` | Set hanging stages back to `ready`. The deployment gets the status which follows from its stages. |

### Stages (v1)

| Method | Path | Permission | Description |
|---|---|---|---|
| `POST` | `/api/run_stage/{meta_file_id}/{stage_id}/{option}` | `run` | Run a stage in the background, now or at a [scheduled time](processing-service.md#scheduled-runs). [Details](#run_stage) |
| `POST` | `/api/cancel_job/{job_id}` | `run` | Remove a stage from the queue of the [processing service](processing-service.md), as long as it hasn't started. Also cancels a scheduled run. |
| `POST` | `/api/reset_stage_status/{meta_file_id}/{stage_id}` | `run` | Set a stage which hangs in `in process` back to `ready`. Possible one minute after its last change, and not while it's in the processing service. |
| `POST` | `/api/reset_last_finished_stage/{meta_file_id}/{stage_id}` | `run` | Set the last finished stage back to `ready` (see [workflow](workflow.md#reset-the-last-finished-stage)). `stage_id` has to be the last finished stage. |
| `GET` | `/show_details/{meta_file_id}/stage/{stage_id}` | `read` | HTML of the steps of a stage, a part of the deployment page (used by the web app) |
| `GET` | `/api/get_stage_steps_html/{meta_file_id}/{stage_id}` | `read` | Deprecated, removed in the next major version: the same HTML as `{"html": ...}` |
| `GET` | `/api/watch_state/{meta_file_id}` | `read` | Server-sent events with hashes of the deployment's state whenever it changes: `page` (the deployment, its stages, jobs, objects and runs), `stages` (one per stage, with its steps, by stage id) and `parts` (`header`, `flow`, `objects`, `activity`: the parts of the deployment page). Used by the web app for its live updates and by the OBI extension |

### Four-eyes check (v1)

| Method | Path | Permission | Description |
|---|---|---|---|
| `POST` | `/api/approve_stage/{meta_file_id}/{stage_id}` | `4-eyes check` (stage) | Approve a stage with `four_eyes_check` ([four-eyes check](permissions.md#four-eyes-check)): `{"approved_by", "time"}`. Not the creator of the deployment (`409`). Step-up |

### Steps and objects (v1)

| Method | Path | Permission | Description |
|---|---|---|---|
| `POST` | `/api/set_check_error/{meta_file_id}/{stage_id}/{action_id}/{checked}` | `change check error` | Turn the error check of a step on (`true`) or off (`false`). Not possible for finished steps or deployments. |
| `POST` | `/api/set_source_ready_4_deployment/{meta_file_id}` | `run` | Include or exclude an object: `{"lib": "devlib", "name": "orders", "type": "file", "checked": true}` |
| `POST` | `/api/set_objects_ready/{meta_file_id}` | `run` | Include or exclude several objects: `{"objects": [{"lib": "devlib", "name": "orders", "type": "file"}, ...], "ready": true}`. Finished objects stay unchanged; the response lists them: `{"status": "success", "changed": 12, "finished": [{"lib": ..., "name": ..., "type": ...}]}`. An unknown object: `404`, nothing is changed. |
| `GET` | `/api/deployment_objects/{meta_file_id}` | `read` | The objects of a deployment as rows of the table of the deployment page: `{"meta_file_id": 6, "can_change": true, "objects": [{"id", "ready", "level", "prod_lib", "lib", "name", "type", "attribute", "source_only", "status", "status_view", "can_change"}]}` |
| `GET` | `/api/deploy_objects` | `read` (only objects of readable workflows) | The object list, one row per object, page by page: `?search=&filter={"project": "erp", "type": "pgm"}&sort=name&order=asc&offset=0&limit=25` → `{"total": 1101, "rows": [{"project", "prod_lib", "name", "type", "attribute", "last_deployment", "deployments"}]}`. Filters: `project`, `type`, `attribute` (value), `prod_lib`, `name` (part); at most 500 rows |
| `GET` | `/list-objects/history?project=&prod_lib=&name=&type=&attribute=` | `read` | HTML of the deployments of an object, a part of the object list (used by the web app) |
| `GET` | `/api/deploy_object_lifecycle/{project}/{prod_lib}/{name}/{type}/{attribute}` | `read` | All deployments of an object |

### Logs and history (v1)

| Method | Path | Permission | Description |
|---|---|---|---|
| `GET` | `/api/get_action_log/{id}` | `read` | One run of a step (`run_history[].id` of the step): status, stdout, stderr |
| `GET` | `/api/get_activity_log/{id}` | `read` | Log of one run of a stage (`run_history[].id` of the deployment) |
| `GET` | `/api/show_processing_history/{meta_file_id}` | `read` | Who did what and when |

### Users and permissions (v1)

| Method | Path | Permission | Description |
|---|---|---|---|
| `POST` | `/api/generate_user_key` | login, session only | A new token named `API token` (scope `write`) for the logged-in user: `{"token": "..."}`. Replaces the one of this name. Needs a recent code (step-up) |
| `POST` | `/api/drop_key` | login, session only | Delete the token named `API token` of the logged-in user |
| `POST` | `/api/revoke_token/{user}` | `admin` | Delete all tokens of a user. Step-up |

### Details (v1)

#### Create a deployment (v1)

Three endpoints create a deployment. They all:

1. load the workflow (by name, not case sensitive);
2. give the deployment the next version number of the workflow's project;
3. create its stages and set `START` to `ready`;
4. call the hook `deployment_created`;
5. return `{"status": "success", "meta_file": {...}}` with the complete deployment.

**`POST /api/start_workflow/{wf_name}`**: the JSON body becomes the custom data of the deployment, as it is:

```json
{"ticket": "ABC-1", "jira": {"ticket": "ABC-1"}}
```

The fields can be limited with [`create_fields`](workflow.md#create-fields) of the workflow. Other fields, or more than 64 KB, are rejected with status 422.

Except the field `compiles`: it's the **compile list** of the deployment (e.g. of an OBI build list), not custom data.

```json
{"timestamp": "2026-11-05 17:39:23", "git": {...}, "compiles": [{"level": 0, "sources": [...]}]}
```

* `timestamp` and `git` become custom data, `compiles` is stored in `compile-list.json` in the meta directory of the deployment.
* It has to be a list and can be up to `C_MAX_COMPILE_LIST_SIZE` (32 MB). Otherwise the request fails with status 422.
* `create_fields` doesn't have to list it.
* Scripts read it with [`meta_file.get_compile_list()`](scripts.md#compile-list).

With an API token also as `GET /api/start_workflow/{wf_name}?ticket=ABC-1`: the query parameters become the custom data (as text). Deprecated.

**`POST /api/create_deployment/{wf_name}/{commit}/{obj_list}`**: no custom data, but:

* `commit` (optional): a commit hash. The request fails with status 409 if another deployment of the project uses the same commit and isn't canceled.
  Stored as `general.commit` and used by the build scripts.
* `obj_list` (optional, also as query parameter `?obj_list=`): path of an [object list](workflow.md#object-list) on the i-Releaser server, imported by the step `load_object_list`.
  It has to be in an allowed directory, otherwise the request fails with status 422.

#### `run_stage`

`POST /api/run_stage/{meta_file_id}/{stage_id}/{option}`

| `option` | |
|---|---|
| `continue` | If the last run of this stage failed, continue with the step which isn't finished |
| `run_all` | Run all steps of the stage again |

Body (optional), to run the stage later ([scheduled run](processing-service.md#scheduled-runs), only in mode `service`):

```json
{"run_at": "2026-11-24T22:00:00+01:00"}
```

`run_at` is ISO 8601 with time zone offset (or `Z` for UTC). Without offset, not a time, or not in the future: status 422. In mode `thread`: status 409.

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"run_at": "2026-11-24T22:00:00+01:00"}' "$URL/api/run_stage/123/456/continue"
```

The stage is run in the background. The response tells how:

```json
{
  "status": "success",
  "mode": "thread|service",
  "job_id": 4711,
  "service_running": true,
  "run_at": "2026-11-24T21:00:00+00:00"
}
```

`job_id`, `service_running` and `run_at` are only returned in mode `service` (see [processing service](processing-service.md)).
`run_at` is the scheduled time in UTC, `null` for a run as soon as possible.
If `service_running` is `false`, the stage stays in the queue until the service has been started.
To cancel a scheduled run before its time: `POST /api/cancel_job/{job_id}` (status 409 once it has started).
The queued and running jobs of a deployment, with their `run_at`, are in `processing_jobs` of `get_meta_file_json`.

Only stages with status `ready` or `failed` can be run, otherwise the request fails with status 409 and nothing changes.
Without `parallel_deployment_execution_allowed`, that's also the case while another stage of the deployment is running.
Follow the progress with `get_meta_file_json`.

#### `edit_custom_data`

`POST /api/edit_custom_data/{meta_file_id}`

```json
{"fields": {"$.ticket": "ABC-2", "$.approval.by": "anna"}}
```

Only the paths in `editable_fields` of the workflow can be changed (see [editable custom fields](workflow.md#editable-custom-fields)).
Calls the hook `custom_data_changed`.
