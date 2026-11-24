# Web API v2

- **Status:** finished (2026-11-24; tested with `tests/test_api_v2.py`. Open, outside of this repository: the OBI extension changes to v2 before v1 is removed, requirement 8)
- **Type:** improvement
- **Priority:** P2
- **Source:** Code review 2026-11-23. The user decided: the API may change if there is a migration; the OBI extension is changed with it.


## Current situation (before)

The [Web API](../webapi.md) has grown with the web pages ([routes.py](../../webapp/routes/routes.py), registered in [index.py](../../webapp/index.py)):

* **Paths:** verbs in the paths (`get_`, `set_`, `show_`, `drop_`, `_4_`), options in the path (`/run_stage/{id}/{stage_id}/{option}`, `/set_check_error/.../{checked}`), snake case and kebab case mixed.
* **Duplicates:** creating a deployment exists as `start_workflow` (GET and POST) and `create_deployment` (3 paths); object selection as `set_source_ready_4_deployment` and `set_objects_ready`; the steps of a stage as `get_stage_steps_html` and `/show_details/.../stage/...`.
* **Answers:** `{status, ...}`, `{}`, plain lists, HTML in JSON; reading `get_meta_file_json` needs `POST`. Errors of FastAPI have another format (see [minor web defects](../bugfixes/minor-web-defects-2026-11.md), item 9).
* **Lists** return everything (except `/api/deploy_objects`), no paging.
* **Tokens:** one per user, no expiry, no scopes.
* **OpenAPI:** all HTML pages are part of it, bodies are untyped `dict`, no security scheme, `/docs` needs a login.


## Requirements

1. New paths under `/api/v2/`, resources and HTTP methods:

   | Method | Path | Instead of |
   |---|---|---|
   | `GET` | `/api/v2/projects` | `/api/get_projects` |
   | `GET` | `/api/v2/workflows` | `/api/get_workflows` |
   | `GET` | `/api/v2/deployments?project=&status=&limit=&cursor=` | `/api/list_deployments/{project}` |
   | `POST` | `/api/v2/deployments` (body: workflow, commit, custom data, compile list, object list) | `start_workflow`, `create_deployment` |
   | `GET` | `/api/v2/deployments/{id}` | `get_meta_file_json` |
   | `POST` | `/api/v2/deployments/{id}/cancel` | `cancel_deployment` |
   | `PATCH` | `/api/v2/deployments/{id}/custom-data` | `edit_custom_data` |
   | `POST` | `/api/v2/deployments/{id}/stages/{stage_id}/runs` (body: `mode` = continue/all, `step`, `run_at`) | `run_stage` |
   | `POST` | `/api/v2/deployments/{id}/stages/{stage_id}/reset` (body: `kind` = hanging/last-finished) | `reset_stage_status`, `reset_last_finished_stage` |
   | `PATCH` | `/api/v2/deployments/{id}/steps/{step_id}` (body: `check_error`) | `set_check_error` |
   | `PATCH` | `/api/v2/deployments/{id}/objects` (body: list of objects with `ready`) | `set_source_ready_4_deployment`, `set_objects_ready` |
   | `GET` | `/api/v2/deployments/{id}/history`, `/steps/{step_id}/log`, `/jobs` | `get_activity_log`, `get_action_log`, `show_processing_history` |
   | `DELETE` | `/api/v2/jobs/{job_id}` | `cancel_job` |
   | `GET`/`POST`/`DELETE` | `/api/v2/tokens` | `generate_user_key`, `drop_key` |

2. One answer format: the resource itself (or `{items, next_cursor}` for lists); errors always `{status: "error", message, error_id?}` with the HTTP status, also for `404`, `405`, `422`.
3. Lists have paging (`limit`, default 50, max 500; `cursor`).
4. **Tokens:** several per user, each with a name, an expiry (max `C_TOKEN_MAX_DAYS`) and a scope: `read` (only `GET`) or `write`. Shown and revoked on the user page; admins can revoke any.
5. OpenAPI: only `/api/v2/` (pages with `include_in_schema=False`), bearer security scheme, tags, request and answer models (pydantic 1 models are possible with FastAPI 0.125; plain `TypedDict` if not).
6. v1 stays as it is, marked as deprecated (header `Deprecation: true` and in `webapi.md`), and is removed in the next major version.
7. The use cases behind v1 and v2 are the same functions (step 5 of the [core redesign](core-redesign.md)); v1 only translates.
8. The OBI extension is changed to v2 (separate project), before v1 is removed.


## Acceptance criteria

- [x] A test per v2 endpoint (success, permission missing, not found, wrong state): `test_every_endpoint_answers_not_found`, `test_every_endpoint_checks_the_permission` (each endpoint of a deployment), and one test per endpoint for the success and its wrong states (e.g. `test_run_a_stage_and_read_its_log`, `test_cancel`, `test_reset_a_deployment`, `test_approve_a_stage`, `test_job_which_has_started_isnt_canceled`).
- [x] Test: the same action with v1 and v2 gives the same result in the database (`test_v1_and_v2_give_the_same_result`).
- [x] Test: a `read` token gets `403` for every non-`GET` request of v2 (`test_read_token_gets_403_for_every_change`).
- [x] Test: `404`, `405`, `422` answer the error format (`test_not_found`, `test_unknown_field_is_refused`, `test_list_with_pages`).
- [x] `webapi.md` describes v2; v1 is in an appendix with the mapping table.


## Non-goals

* GraphQL, webhooks as part of the API (see [notifications](notifications.md)).
* Removing v1 in this feature.


## Decisions (2026-11-24)

* **Use cases:** `modules/application/deployments.py` has one function per action (create, cancel, run, reset, edit custom data, approve, objects, check error, cancel job, history). It checks the permission and writes the history. The handlers of v1 (`routes/routes.py`) and v2 (`routes/api_v2.py`) only translate paths and bodies (requirement 7, a part of step 5 of the [core redesign](core-redesign.md)).
* **Paths** as in the table of the requirements, plus `POST /deployments/{id}/reset` (v1 `reset_deployment_status`) and `POST /deployments/{id}/stages/{stage_id}/approvals` (v1 `approve_stage`). Not in v2 yet (no client needs them as API): the object list (`/api/deploy_objects`), the live updates (`/api/watch_state`), the admin actions. They keep their paths and aren't deprecated.
* **Answers:** `201` with the new deployment or token, `202` for a run, `204` for a deletion. The deployment has the same JSON as v1 (`get_meta_file_json`), so a client changes only its paths. The log of a step contains the output itself, not the path of its file on the server.
* **Bodies:** pydantic 1 models with `extra = 'forbid'` (a typo of a field is `422`) and `StrictBool` (pydantic 1 would read `"no"` as `false`).
* **Paging** of the deployments with a cursor (the last id, base64), newest first. The other lists are short (history, jobs, runs of a step, tokens): one page, `next_cursor` is `null`.
* **Tokens** (requirement 4) in the table `api_tokens`: name (unique per user), scope `read` or `write`, expiry (days, at most `C_TOKEN_MAX_DAYS`), at most 20 per user. New tokens start with `irt_` (secret scanners, logs). The tokens of `webapp/etc/keys.json` are taken over at the start of the web app (and when the file appears again), as `API token` with scope `write`; the file is renamed to `keys.json.migrated`. v1 `generate_user_key` replaces the token `API token`, `drop_key` deletes it, `revoke_token/{user}` deletes all tokens of the user.
* **Scope `read`** is checked by the middleware for all paths (v1 too): only `GET`, `HEAD`, `OPTIONS`, and the two reads of v1 with `POST` (`get_meta_file_json/{id}`, `list_deployments/{project}`, exact paths: `webmiddleware.V1_READ_POSTS`), because the OBI extension reads a deployment with `POST`. Tested with `test_tokens_with_name_scope_and_expiry`.
* **OpenAPI** (`/docs`, `/openapi.json`) shows only `/api/v2/`, with the bearer scheme, tags and the models of the bodies; the pages, v1 and custom routes have `include_in_schema = False`.
* **v1** answers with the header `Deprecation: true` (the paths which v2 replaces, `webmiddleware.V1_DEPRECATED`). The pages of the web app still call some v1 paths; they change to v2 before v1 is removed.
* Separation of pages and API (open question): `/api/v2/` works with a token or with the session (the same rules as today: same origin for changes); tokens can't manage tokens.


## Open questions (answered 2026-11-24, the proposals)

* Should HTML pages and the API be separated further (pages only with session, API only with token)? Proposal: yes for v2: `/api/v2/` only with token or with session plus `X-Requested-With`, as today.
* Version in the path (`/api/v2/`) or in a header? Proposal: path (simple for scripts and curl).
