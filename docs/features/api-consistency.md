# Consistent Web API responses

- **Status:** finished
- **Type:** improvement
- **Priority:** P3


## Current situation

* Almost every error is answered with status 500, including missing permissions and invalid input.
* `create_deployment` answers a used commit with 401 and the key `error`; other errors use `message`.
* The text of the Python exception is returned as message. It can contain internal details (paths, SQL, stack information).
* A request to `/api/...` without login gets the HTML login page with status 200 if it accepts `*/*` (the default of `curl`).
* Actions which change data are `GET` requests (see [CSRF](../bugfixes/csrf-actions-via-get.md)), and the token is only accepted in the URL (see [API token](../bugfixes/api-token-stored-in-custom-data.md)).


## Requirements

1. Status codes:

   | Case | Status |
   |---|---|
   | Invalid input | 400 or 422 |
   | Not logged in, invalid token | 401 |
   | Missing permission | 403 |
   | Deployment, stage, job not found | 404 |
   | Not possible in the current status (e.g. stage already running, commit already used) | 409 |
   | Unexpected error | 500 |

2. All errors have the same body: `{"status": "error", "message": "..."}`.
3. Unexpected errors (500) return a general message with an error id. The details are only in the log, with that id.
4. Requests to `/api/...` never get the login page. Without login they get 401 JSON.
5. Permission errors are a separate exception class, so the status can be set in one place (middleware or exception handler).
6. `docs/webapi.md` documents the status codes.


## Acceptance criteria

- [x] Tests for each status code with at least one endpoint.
- [x] Test: an unexpected exception → 500 with error id, no exception text in the response, the id is in the log.
- [x] Test: `curl` without login on `/api/get_projects` → 401 JSON.
- [x] The web app shows the messages as before.


## Non-goals

* A new API version or new endpoints


## Decisions

* OpenAPI description (`/docs`)? **Keep it as it is today: only for logged-in users.**
