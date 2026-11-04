# One invalid workflow file must not stop the web app

- **Status:** finished
- **Type:** improvement
- **Priority:** P2


## Current situation

`Workflow.get_all_workflows_json` raises an exception at the first invalid file in `etc/workflows/` ([workflow.py:167](../../modules/workflow.py#L167)).

The sidebar of every page lists the projects (`get_all_projects`, which reads all workflows).
So one invalid file (a typo while editing) makes **every page** of the web app fail, and no stage can be created.


## Requirements

1. Invalid workflow files are skipped. The valid workflows keep working.
2. The error is logged with file name and reason.
3. The page `Workflows` shows invalid files with their error (for users with `admin`, or all, see open questions).
4. Existing deployments of a workflow whose file is invalid can still be opened and run (the definition is stored with the deployment).
5. Creating a deployment of an invalid workflow fails with a clear message.


## Acceptance criteria

- [x] Test: one valid and one invalid file → pages work, the valid workflow can be used, the invalid one is listed with its error.
- [x] Test: a deployment created before its file became invalid can still run its stages.
- [x] Test: creating a deployment of the invalid workflow → error message with the file name.


## Non-goals

* Editing workflows in the web app


## Decisions

* Who sees the errors? **Users with `admin`.**
