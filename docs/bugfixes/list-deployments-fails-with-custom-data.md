# `/api/list_deployments` fails if a deployment has custom data

- **Status:** finished
- **Type:** bug
- **Priority:** P2
- **Found:** 2026-10-23, reproduced


## Current situation

`list_deployments` ([routes.py:107](../../webapp/routes/routes.py#L107)) returns the rows of `Deploy_Version.get_deployments` as they are (`SELECT mf.*, ...`).
The column `custom_data` contains compressed bytes, which can't be converted to JSON:

```
TypeError: Object of type bytes is not JSON serializable
```

So the endpoint fails with 500 as soon as one deployment of the project has custom data.
The other columns are internal too (e.g. `meta_dir`, `deploy_version_id`).


## Requirements

1. The endpoint returns a defined list of fields per deployment: `meta_file_id`, `version`, `status`, `workflow_name`, `commit`, `create_time`, `update_time`, and the custom data as JSON (decompressed).
2. Timestamps in ISO format.
3. Only deployments of workflows the user may read (see [missing permission checks](missing-permission-checks.md)).
4. Document the fields in `docs/webapi.md`.


## Acceptance criteria

- [x] Regression test: a project with a deployment with custom data → 200, the custom data is returned as JSON object.
- [x] Test: a project without deployments → empty list.


## Non-goals

* Paging


## Decisions

* Custom data in the list? **No. It's in `get_meta_file_json`.**
