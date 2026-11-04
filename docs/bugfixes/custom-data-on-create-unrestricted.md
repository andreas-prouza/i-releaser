# Any custom data can be set when a deployment is created

- **Status:** finished
- **Type:** security
- **Priority:** P1
- **Found:** 2026-10-23, code review
- **Confidential:** don't publish before the fix is released


## Current situation

`editable_fields` of a workflow limits which fields of the custom data users can **edit**.
But when a deployment is created (`POST`/`GET /api/start_workflow/{wf_name}`, [routes.py:566](../../webapp/routes/routes.py#L566), [routes.py:599](../../webapp/routes/routes.py#L599)), any JSON is accepted as custom data, without a size limit.

So every user with `start workflow` can set fields which other parts trust:

* `$.db_deployment`: which production tables the DB deployment replaces and the SQL expressions of their columns, run by a DB user with far-reaching authorities;
* fields used in [command placeholders](command-placeholders-with-user-input.md) or by hooks (e.g. Jira issue keys).


## Requirements

1. A workflow defines which custom data fields may be set when a deployment is created (see open questions).
2. Other fields are rejected with 422 and a message which names them. They are not dropped silently.
3. The custom data has a maximum size (e.g. 64 KB).
4. The same rules apply to the `GET` and `POST` variant.
5. Update `docs/workflow.md` and `docs/webapi.md`.


## Acceptance criteria

- [x] Test: allowed fields are stored as before.
- [x] Test: a field which isn't allowed (e.g. `db_deployment`) → 422, no deployment created.
- [x] Test: custom data over the size limit → 422.


## Non-goals

* [Validation of the DB deployment names](db-deployment-name-validation.md)


## Decisions

* New attribute or `editable_fields`? **New optional workflow attribute `create_fields`. Without it all fields stay allowed, except `db_deployment`. (Your custom rollback template passes its own parameters.)**
* DB deployment configuration when creating? **Only if `$.db_deployment` is listed in `create_fields`. Otherwise with `edit-custom-data`.**
