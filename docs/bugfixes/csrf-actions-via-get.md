# Actions can be triggered by a link (CSRF)

- **Status:** finished
- **Type:** security
- **Priority:** P1
- **Found:** 2026-10-23, reproduced on a copy of the web app
- **Confidential:** don't publish before the fix is released


## Current situation

Many actions change data with a `GET` request, and the session cookie is the only check:

| Endpoint | Action |
|---|---|
| `/api/run_stage/{meta_file_id}/{stage_id}/{option}` | Run a stage, e.g. the production deployment |
| `/api/cancel_deployment/{meta_file_id}` | Cancel a deployment |
| `/api/cancel_job/{job_id}` | Remove a stage from the queue |
| `/api/reset_stage_status/...`, `/api/reset_last_finished_stage/...`, `/api/reset_deployment_status/...` | Reset status |
| `/api/set_check_error/...` | Turn off the error check of a step |
| `/api/create_deployment/...`, `GET /api/start_workflow/...` | Create a deployment |

The session cookie has `SameSite=Lax`: the browser sends it when a user follows a link or is redirected from another site.
A link in a mail or on another page can therefore run a stage in the name of a logged-in user.

Reproduction: `GET /api/create_deployment/seq_wf` with only the session cookie → a deployment is created.


## Requirements

1. With a session cookie, data can only be changed with `POST` (or `PUT`/`DELETE`).
2. For these requests the server checks that `Origin` (or `Referer`) is the own host (as seen through the reverse proxy), or uses a CSRF token.
3. Requests authenticated with an API token (no cookie) are not affected by the origin check.
4. The web app uses `POST` for these actions (`show-deployment.html`, `admin/workflows.html`, and the example in `custom_templates`).
5. Update `docs/webapi.md`.


## Acceptance criteria

- [x] Test: each endpoint above called with `GET` and only a session cookie → rejected (405 or 403), nothing changed.
- [x] Test: `POST` with session cookie and a foreign `Origin` → 403.
- [x] Test: `POST` with session cookie and the own origin → works. All buttons of the web app work.
- [x] Test: API calls with a token keep working.


## Non-goals

* [CORS](cors-allows-any-origin.md)


## Decisions

* Keep `GET` for API clients? **Yes for requests with an API token, marked as deprecated. Requests with a session cookie need `POST`. No breaking change for API clients.**
* `SameSite=Strict`? **No, stay with `Lax`. Links from mails keep working.**
