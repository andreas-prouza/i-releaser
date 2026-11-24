# Health check

- **Status:** finished (2026-11-24; tested with `tests/test_health_check.py`, not on IBM i)
- **Type:** feature
- **Priority:** P3
- **Source:** Code review 2026-11-23


## Current situation

Every path except `/static/` needs a login ([webmiddleware.py](../../webapp/routes/webmiddleware.py)).
A monitoring tool (Nagios, Zabbix, Uptime Kuma, the load balancer of the reverse proxy) can only check whether the login page answers, not whether the database or the processing service work.
That the processing service isn't running is only seen when a run stays in the queue (the page shows a warning).


## Requirements

1. `GET /healthz` without login. Answer `200` with `{"status": "ok"}`, or `503` with `{"status": "error", "checks": {...}}`.
2. Checks (each with a short timeout):
   * database: a `SELECT 1` and the schema version matches,
   * processing service: running (lock file / last heartbeat), only if the processing mode is `service`,
   * free space of the IFS directory of `var/` and `meta/` above `C_HEALTH_MIN_FREE_MB`.
3. Without login the answer contains no version, no paths, no names (only `ok`/`error` per check). With login (or token) it also has the version and the details.
4. `/healthz` is excluded from the access log at level `INFO` (it's called every few seconds).
5. `installation.md` shows how to use it with the reverse proxy and a monitoring tool.


## Acceptance criteria

- [x] Test: `/healthz` without login answers `200` and contains only the status.
- [x] Test: with a database which can't be opened it answers `503`.
- [x] Test: mode `service` without running service answers `503` with check `processing_service: error`.


## Non-goals

* Metrics (Prometheus) with durations and counts. Could follow if needed.


## Decisions (2026-11-24)

* A stopped processing service is an error in mode `service` (proposal accepted).
* `C_HEALTH_MIN_FREE_MB` (default 500) for the free space of `var/` and `meta/`.
* The answer has no cookie: the check doesn't create a session.


## Open questions (answered 2026-11-24)

* Should a stopped processing service be an error (`503`) or a warning (`200` with a note)? Proposal: error in mode `service`, as no stage can run.
