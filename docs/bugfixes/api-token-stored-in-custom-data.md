# API token is stored in the custom data and logged

- **Status:** finished
- **Type:** security
- **Priority:** P0
- **Found:** 2026-10-23, reproduced on a copy of the web app
- **Confidential:** don't publish before the fix is released


## Current situation

`GET /api/start_workflow/{wf_name}` uses all query parameters as custom data of the new deployment, including `auth-token`
([routes.py:570](../../webapp/routes/routes.py#L570)), and logs them at `INFO` ([routes.py:571](../../webapp/routes/routes.py#L571)).

Reproduction: `GET /api/start_workflow/seq_wf?auth-token=<token>&ticket=ABC-1` → custom data `{"auth-token": "<token>", "ticket": "ABC-1"}`, and the token is in the web app log.

Consequences:

* Everyone with `read` on the workflow sees the token in the custom data and can act as its owner.
* Hooks get it (e.g. sent to Jira).
* It's stored in the database and in the logs.

In addition, the token is only accepted as query parameter, so it's also in the access logs of uvicorn/gunicorn and the reverse proxy.


## Requirements

1. `auth-token` is never part of custom data or any other stored data.
2. Credentials in requests (query parameters, bodies, headers) are never logged.
3. The token is accepted in the header `Authorization: Bearer <token>`. The query parameter `auth-token` keeps working for compatibility (see open questions).
4. Database update: remove the key `auth-token` from the custom data of existing deployments.
5. Documentation: the examples in `docs/webapi.md` use the header. The changelog advises to generate new tokens.


## Acceptance criteria

- [x] Test: `GET /api/start_workflow/...?auth-token=...&a=1` → custom data is `{"a": "1"}`.
- [x] Test: after this request, no log file contains the token.
- [x] Test: all endpoints accept `Authorization: Bearer <token>`. An invalid token gets 401.
- [x] Test: the database update removes `auth-token` from existing custom data and leaves the other keys.


## Non-goals

* Expiry of tokens (see [weak API tokens](weak-api-tokens.md))


## Decisions

* When to remove the query parameter `auth-token`? **Keep it, mark it as deprecated. Remove it in a later major version.**
* Keep the `GET` variant of `start_workflow`? **Keep it for requests with an API token (see CSRF).**
