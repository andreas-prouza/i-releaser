# Web app: no blocking work in async handlers

- **Status:** finished
- **Type:** improvement
- **Priority:** P3


## Current situation

* All route handlers are `async def`, but they read the database, files and templates synchronously.
  While one request does that, no other request of the same worker is served.
* Each open deployment page asks every 2 seconds for changes (`watch_state`). Each check loads the whole deployment (all stages, steps, objects) from the database.
* `get_html_response` creates a new `Jinja2Templates` for every response, so templates are compiled again each time ([http_functions.py:59](../../webapp/web_modules/http_functions.py#L59)).
  The deployment page renders a template for each stage.
* Each status change of a deployment loads all deployments of the project with all columns (`validate_deployment`), and the commit check reads the details of all of them.


## Requirements

1. Handlers which do blocking work are plain `def` (FastAPI runs them in a thread pool) or move the work to a thread.
2. One template environment for the web app.
3. `watch_state` detects changes with a small query (e.g. a change counter or `update_time` of deployment and stages), and only loads the deployment if something has changed.
4. `validate_deployment` and the commit check use targeted queries (older open deployments of the project; deployment with this commit), with indexes.
5. Measure before and after (see acceptance criteria).


## Acceptance criteria

- [x] Test: while one request takes 5 seconds (e.g. a slow database query in a test hook), other requests of the same worker are answered.
- [x] Measurement: deployment page with 20 stages and 500 objects is rendered faster than today (numbers in this file).
- [x] Measurement: 10 open deployment pages cause less than today's database load (queries per minute).


## Measurements

Deployment with 20 stages and 500 objects, one worker, log level `INFO`, 2026-11-01:

| | Before | After |
|---|---|---|
| Deployment page (median of 15) | 81 ms | 59 ms |
| Check of an open page, without a change (every 2 seconds per page) | 45 ms | 0.11 ms |

So 10 open pages cost 4.5 % instead of 0.005 % of a core for these checks.


## Non-goals

* Another database


## Decisions

* Target values? **No fixed targets: measure before and after, and record the numbers.**
