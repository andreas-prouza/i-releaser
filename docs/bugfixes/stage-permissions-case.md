# Permissions for a stage with capital letters never apply

- **Status:** finished (2026-11-19; tested with `tests/test_permission_names.py` and `tests/test_deployment_page.py`, not on IBM i)
- **Type:** bug
- **Priority:** P1
- **Found:** 2026-11-19, test of the [deployment page](../features/web-ui-deployment-page.md) (a user with `run` for the stage `PROD` only)


## Current situation

* The permissions page saves a stage with its name from the workflow, e.g. `"stages": {"PROD": ["run"]}` ([settings.html](../../webapp/templates/admin/settings.html), `add_user_workflow_stage`). The same for workflows: their name as it is.
* The check looks for the name in lower case (`stage.lower() in current_wf['stages']`, [permission_config.py](../../modules/permission_config.py)), the workflow too.
* So a permission for the stage `PROD`, added in the web app, is never used: the user can't run the stage. Only files written by hand in lower case (as in [permissions.md](../permissions.md)) work. Stage names are usually written in capitals (`START`, `PROD`).


## Requirements

1. Names of workflows and stages in the permissions are compared without case, whichever way they are written in `etc/user_permissions.json`.
2. Files which work today keep working (lower case).


## Acceptance criteria

- [x] Test: a permission for the stage written `PROD`, `prod` or `Prod` applies to the stage `PROD`; not to another stage or another action.
- [x] Test: the same for the name of the workflow.
- [x] Test: on the deployment page a user with `run` for `PROD` only can run `PROD` and not `START`.


## Implementation

`permission_config.is_permission_allowed` builds the lookup of workflows and stages with lower-case keys.


## Open questions

None.
