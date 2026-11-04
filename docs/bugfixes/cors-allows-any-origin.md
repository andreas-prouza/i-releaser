# CORS allows any origin with credentials

- **Status:** finished
- **Type:** security
- **Priority:** P1
- **Found:** 2026-10-23, reproduced on a copy of the web app
- **Confidential:** don't publish before the fix is released


## Current situation

The web app adds `CORSMiddleware` with `allow_origins=["*"]` and `allow_credentials=True` ([initial.py:48](../../webapp/routes/initial.py#L48)).
Starlette then answers credentialed requests with the origin of the request:

```
GET /api/get_projects   Origin: https://evil.example   Cookie: session_id=...
→ access-control-allow-origin: https://evil.example
  access-control-allow-credentials: true
```

Preflight requests (`OPTIONS`) from any origin are allowed in the same way.

So scripts of other web sites can read all responses and send requests in the name of a logged-in user,
as far as the browser sends the session cookie (`SameSite=Lax`: e.g. from other applications on the same host or domain).


## Requirements

1. No CORS headers by default. Remove `CORSMiddleware` or configure it with an explicit list of origins.
2. Optional setting (e.g. `C_CORS_ALLOWED_ORIGINS` in `webapp/etc/`), default empty. `*` is not allowed together with credentials.
3. Document the setting in `docs/installation.md`.


## Acceptance criteria

- [x] Test: request with `Origin: https://evil.example` and a session cookie → no `Access-Control-Allow-Origin` header.
- [x] Test: preflight from a foreign origin → no allow headers.
- [x] Test: a configured origin gets the CORS headers.
- [x] The web app works unchanged (same origin).


## Non-goals

* [CSRF protection](csrf-actions-via-get.md)


## Decisions

* Browser clients on another origin? **Assume none. No CORS by default, optional list of origins.**
