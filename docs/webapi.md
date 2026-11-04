# Web API

* [Authentication](#authentication)
* [Responses and errors](#responses-and-errors)
* [Example: create a deployment and run a stage](#example-create-a-deployment-and-run-a-stage)
* [Endpoints](#endpoints)
  * [Deployments](#deployments)
  * [Stages](#stages)
  * [Steps and objects](#steps-and-objects)
  * [Logs and history](#logs-and-history)
  * [Users and permissions](#users-and-permissions)
* [Details](#details)

All actions of the web app are available as HTTP endpoints. They use the same [permissions](permissions.md) as the web app.

`meta_file_id` is the internal id of a deployment (`general.id` in its JSON), not its version.
Stage ids are in `general.open_stages[].id` and `general.processed_stages[].id`.


## Authentication

Two ways:

* **API token** (for other applications): generate a token on the user page of the web app (`/user`) and send it in the header `Authorization`:

  ```
  Authorization: Bearer 4f9c...e1
  ```

  The request runs with the permissions of the user who owns the token. See [API tokens](permissions.md#api-tokens).

  The query parameter `?auth-token=4f9c...e1` still works, but it's deprecated: URLs end up in the logs of proxies.

* **Session** (the web app): log in with a form post of `user` and `password` (e.g. to `/`). The session cookie `session_id` is valid for one hour after the last request.
  Requests with a session have to come from the web app itself: requests which change data need `POST` and an `Origin` (or `Referer`) header of the own host.

Use HTTPS.

Without a valid login `/api/...` answers with status 401:

```json
{"status": "error", "message": "You are not logged in"}
```


## Responses and errors

Responses are JSON. Actions return `{"status": "success", ...}`.

All errors have the same format:

```json
{"status": "error", "message": "User anna does not have permission PermissionAction.RUN_WORKFLOW (workflow: erp_release, stage: PROD)"}
```

| Status | Meaning |
|---|---|
| 401 | Not logged in, or invalid token |
| 403 | Missing permission, or a request with a session from another origin |
| 404 | Deployment, stage, job or workflow not found |
| 405 | Action sent as `GET` with a session |
| 409 | Not possible in the current status, e.g. the stage isn't ready or the commit is already used |
| 422 | Invalid input |
| 500 | Unexpected error. The message contains an error id to find the details in the log. |


## Example: create a deployment and run a stage

```bash
URL=https://ireleaser.example.com
TOKEN=4f9c...e1

# Create a deployment of workflow erp_release with custom data
curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"ticket": "ABC-1"}' \
     "$URL/api/start_workflow/erp_release"
# {"status": "success", "meta_file": {"general": {"id": 123, "deploy_version": 42,
#   "open_stages": [{"id": 456, "name": "START", "status": "ready", ...}, ...], ...}, ...}}

# Run stage START (id 456) of deployment 123
curl -s -X POST -H "Authorization: Bearer $TOKEN" "$URL/api/run_stage/123/456/continue"
# {"status": "success", "mode": "thread"}

# Follow its status
curl -s -X POST -H "Authorization: Bearer $TOKEN" "$URL/api/get_meta_file_json/123"
```


## Endpoints

Permission "login" means: any logged-in user, no further permission is checked.
Lists only contain what the user may read.

Actions which change data are shown with `POST`. With an API token they also work with `GET`, but that's deprecated.

### Deployments

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

### Stages

| Method | Path | Permission | Description |
|---|---|---|---|
| `POST` | `/api/run_stage/{meta_file_id}/{stage_id}/{option}` | `run` | Run a stage in the background. [Details](#run_stage) |
| `POST` | `/api/cancel_job/{job_id}` | `run` | Remove a stage from the queue of the [processing service](processing-service.md), as long as it hasn't started |
| `POST` | `/api/reset_stage_status/{meta_file_id}/{stage_id}` | `run` | Set a stage which hangs in `in process` back to `ready`. Possible one minute after its last change, and not while it's in the processing service. |
| `POST` | `/api/reset_last_finished_stage/{meta_file_id}/{stage_id}` | `run` | Set the last finished stage back to `ready` (see [workflow](workflow.md#reset-the-last-finished-stage)). `stage_id` has to be the last finished stage. |
| `GET` | `/api/get_stage_steps_html/{meta_file_id}/{stage_id}` | `read` | HTML of the steps of a stage (used by the web app) |
| `GET` | `/api/watch_state/{meta_file_id}` | `read` | Server-sent events with a hash of the deployment's state whenever it changes (used by the web app for its auto refresh) |

### Steps and objects

| Method | Path | Permission | Description |
|---|---|---|---|
| `POST` | `/api/set_check_error/{meta_file_id}/{stage_id}/{action_id}/{checked}` | `change check error` | Turn the error check of a step on (`true`) or off (`false`). Not possible for finished steps or deployments. |
| `POST` | `/api/set_source_ready_4_deployment/{meta_file_id}` | `run` | Include or exclude an object: `{"lib": "devlib", "name": "orders", "type": "file", "checked": true}` |
| `GET` | `/api/deploy_object_lifecycle/{project}/{prod_lib}/{name}/{type}/{attribute}` | `read` | All deployments of an object |

### Logs and history

| Method | Path | Permission | Description |
|---|---|---|---|
| `GET` | `/api/get_action_log/{id}` | `read` | One run of a step (`run_history[].id` of the step): status, stdout, stderr |
| `GET` | `/api/get_activity_log/{id}` | `read` | Log of one run of a stage (`run_history[].id` of the deployment) |
| `GET` | `/api/show_processing_history/{meta_file_id}` | `read` | Who did what and when |

### Users and permissions

| Method | Path | Permission | Description |
|---|---|---|---|
| `POST` | `/api/generate_user_key` | login | New API token for the logged-in user: `{"token": "..."}`. Replaces the old one. |
| `POST` | `/api/drop_key` | login | Delete the API token of the logged-in user |
| `POST` | `/api/add_permission` | `admin` | Add a user or role: `{"type": "user"\|"role", "name": "anna", "general": ["read"]}` |
| `POST` | `/api/save_permissions` | `admin` | Replace all users and roles (`{"user_permissions": {...}, "role_permissions": {...}}`, like `etc/user_permissions.json`) |


## Details

### Create a deployment

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

With an API token also as `GET /api/start_workflow/{wf_name}?ticket=ABC-1`: the query parameters become the custom data (as text). Deprecated.

**`POST /api/create_deployment/{wf_name}/{commit}/{obj_list}`**: no custom data, but:

* `commit` (optional): a commit hash. The request fails with status 409 if another deployment of the project uses the same commit and isn't canceled.
  Stored as `general.commit` and used by the build scripts.
* `obj_list` (optional, also as query parameter `?obj_list=`): path of an [object list](workflow.md#object-list) on the i-Releaser server, imported by the step `load_object_list`.
  It has to be in an allowed directory, otherwise the request fails with status 422.

### `run_stage`

`POST /api/run_stage/{meta_file_id}/{stage_id}/{option}`

| `option` | |
|---|---|
| `continue` | If the last run of this stage failed, continue with the step which isn't finished |
| `run_all` | Run all steps of the stage again |

The stage is run in the background. The response tells how:

```json
{
  "status": "success",
  "mode": "thread|service",
  "job_id": 4711,
  "service_running": true
}
```

`job_id` and `service_running` are only returned in mode `service` (see [processing service](processing-service.md)).
If `service_running` is `false`, the stage stays in the queue until the service has been started.

Only stages with status `ready` or `failed` can be run, otherwise the request fails with status 409 and nothing changes.
Without `parallel_deployment_execution_allowed`, that's also the case while another stage of the deployment is running.
Follow the progress with `get_meta_file_json`.

### `edit_custom_data`

`POST /api/edit_custom_data/{meta_file_id}`

```json
{"fields": {"$.ticket": "ABC-2", "$.approval.by": "anna"}}
```

Only the paths in `editable_fields` of the workflow can be changed (see [editable custom fields](workflow.md#editable-custom-fields)).
Calls the hook `custom_data_changed`.
