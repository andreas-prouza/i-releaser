# Host header skips the login check

- **Status:** finished
- **Type:** security
- **Priority:** P1
- **Found:** 2026-11-02, code review, reproduced
- **Confidential:** don't publish before the fix is released


## Current situation

`webapp/routes/webmiddleware.py` decided on `request.url.path`. Starlette builds this URL with the `Host` header, which the client chooses.
With `Host: x/static/` the path of `/api/get_workflows` became `/static/api/get_workflows`: the login check was skipped, but the router still ran `/api/get_workflows`.
The same worked with `/favicon.ico` and `/logout`, and it skipped the check of actions sent with `GET` (`ACTIONS_WITHOUT_GET`).

The permission checks still blocked data and actions (no user), so the effect was limited to routes without a permission check.


## Requirements

1. The middleware decides on the path the router uses (`request.scope['path']`), not on the URL built with the `Host` header.


## Acceptance criteria

- [x] A request without login gets `401`, whatever the `Host` header is (`test_host_header_does_not_skip_the_login_check`).
- [x] An action with `GET` and a session gets `405`, whatever the `Host` header is (`test_host_header_does_not_allow_actions_with_get`).
- [x] All tests pass.


## Non-goals

* Checking the `Host` header against a list of allowed hosts
