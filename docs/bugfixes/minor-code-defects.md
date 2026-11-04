# Minor code defects

- **Status:** finished
- **Type:** bug
- **Priority:** P3
- **Found:** 2026-10-23, code review

Small defects without their own file. Each can be fixed on its own.


## Defects

| # | Defect | Where | Expected |
|---|---|---|---|
| 1 | Debug leftovers `logging.warning("XXXXX ...")` on every deployment page | [routes.py:269](../../webapp/routes/routes.py#L269) | Removed |
| 2 | `logging.error` for the normal number of listed objects | [routes.py:84](../../webapp/routes/routes.py#L84) | `debug` |
| 3 | `Run all` still skips failed steps without error check: `continue_run and FINISHED or (FAILED and not check_error)` | [ibm_i_commands.py:83](../../modules/ibm_i_commands.py#L83) | Decide and document; add parentheses (see open questions) |
| 4 | `with get_db_connection() as conn` commits, but doesn't close the connection | [app_sqlite.py:29](../../modules/db/app_sqlite.py#L29) and all callers | Connections are closed (context manager which closes) |
| 5 | `user_permissions.json` and `keys.json` are written in place. A crash while writing leaves an invalid file, and then nobody can log in. Two workers writing `keys.json` at the same time lose a token. | [files.py:102](../../modules/files.py#L102) | Write to a temporary file and rename; lock while changing |
| 6 | The flowchart is built in module level globals (`flow_stages`, `flow_connection`) | [flowchart.py:31](../../webapp/web_modules/flowchart.py#L31) | Local state per request |
| 7 | `Deploy_Version.get_deployment` raises instead of returning `None`, but `show_details` checks for `None` | [deploy_version.py:181](../../modules/deploy_version.py#L181), [routes.py:242](../../webapp/routes/routes.py#L242) | "Not found" page with 404 |
| 8 | `create_deployment` answers a used commit with status 401 and the key `error` instead of `message` | [routes.py:546](../../webapp/routes/routes.py#L546) | 409, same format as other errors (see [API consistency](../features/api-consistency.md)) |


## Acceptance criteria

- [x] Each fixed defect has a unit test, where it can be tested (3, 4, 5, 7, 8).
- [x] No `XXXXX` in the code.


## Non-goals

* [Dead code](../features/dead-code-cleanup.md)


## Decisions

* Should `Run all` also run failed steps without error check? **Yes.**
