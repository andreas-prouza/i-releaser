# Requests can run with the permissions of another user

- **Status:** finished
- **Type:** security
- **Priority:** P0
- **Found:** 2026-10-23, reproduced on a copy of the web app
- **Confidential:** don't publish before the fix is released


## Current situation

The user of a request is stored in the class attribute `Meta_File.CURRENT_USER`. All requests of a worker process share it.
The middleware sets it and then waits for the handler. Meanwhile another request sets it to its own user.
The permission checks (`check_user_permission`) read this attribute.

Reproduction:

1. User `intern` (permissions `read`, `start workflow`) requests the admin page `/settings` 300 times, 15 in parallel.
2. At the same time user `boss` (permission `admin`) requests `/api/get_stage_steps_html/{id}/{stage}` 300 times (like an open deployment page).
3. Result: 53 of the 300 requests of `intern` got the settings page.

Consequences:

* Any logged-in user can act with the permissions of another active user, including `admin`: run production stages, change permissions.
* The activity history (`processing_users`) and jobs of the processing service may record the wrong user.
* In thread mode, a running stage reads the attribute when it writes its activity log, so it records whoever made the last request.


## Cause

* Set: [webmiddleware.py:113](../../webapp/routes/webmiddleware.py#L113), [webmiddleware.py:124](../../webapp/routes/webmiddleware.py#L124), [app_login.py:39](../../webapp/web_modules/app_login.py#L39), [processing_service.py:125](../../modules/processing_service.py#L125)
* Read: [permission_config.py:16](../../modules/permission_config.py#L16), [processing_user.py:14](../../modules/processing_user.py#L14), [meta_file.py:454](../../modules/meta_file.py#L454), [routes.py:271](../../webapp/routes/routes.py#L271)


## Requirements

1. The user of a request belongs to that request only, e.g. a `contextvars.ContextVar` set by the middleware, or `request.state.user` passed on explicitly. No mutable user on module or class level.
2. `check_user_permission` and `is_user_allowed` get the user of the current request (context or parameter).
3. Work which outlives the request gets the user explicitly:
   * stage threads (thread mode): `threading.Thread` doesn't copy the context, so pass the user or run the target with `contextvars.copy_context().run`;
   * jobs of the processing service (already store `job.user`);
   * hooks and activity logs.
4. Code without a request (processing service, command line) sets the user explicitly. A missing user means "no permission", never "the previous user".
5. No handler runs with a user set if the request has no valid login.


## Acceptance criteria

- [x] Regression test: two users with different permissions send concurrent requests (e.g. 300 each, 15 in parallel). The user without `admin` never gets `/settings`.
- [x] Regression test: a stage started by user A in thread mode records A in its log and activity history, although user B makes requests while it runs.
- [x] A job queued by user A runs as A in the processing service.
- [x] No mutable user state on class or module level is left (`grep -rn CURRENT_USER`), except a `ContextVar`.


## Non-goals

* Changes of the permission model itself
