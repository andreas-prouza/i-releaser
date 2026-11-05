# OBI can't start a workflow: the build list is larger than the custom data limit

- **Status:** finished
- **Type:** bug (regression)
- **Priority:** P1
- **Found:** 2026-11-05, reproduced with OBI 1.5.3


## Current situation

OBI (VS Code extension) starts a workflow with `POST /api/start_workflow/{wf_name}`.
The body is its build list (`timestamp`, `compiles`, `git`, without the command logs), and i-Releaser stores the whole body as custom data.

Since [custom data on create is limited](custom-data-on-create-unrestricted.md) to 64 KB, this fails:

```
Starting the i-Releaser workflow failed: Error: HTTP 422: Custom data is larger than 65536 bytes
```

A build list with 6 levels and 33 sources is already ~290 KB. Most of it is `compiles[].sources[].variables` and `cmds[].properties`.
OBI can't leave them out: `scripts/obi.py` (`load_objects_from_compile_list`) needs them to create the deploy objects.

Also: deployments which already have a compile list over 64 KB in their custom data can't be edited any more (e.g. `jira.ticket-id`), because an edit checks the size of the whole custom data.


## Requirements

1. The field `compiles` of the body of `POST /api/start_workflow/{wf_name}` is the compile list of the deployment. It's stored separately, not in the custom data.
2. Everything else in the body stays custom data, with the same rules as before (`create_fields`, 64 KB).
3. OBI 1.5.3 works without a change.
4. Scripts read the compile list with `meta_file.get_compile_list()`. Deployments created before have it in `custom_data.compiles`, which is returned as fallback.
5. The compile list is there when the hook `deployment_created` and the first stages (`run_immediate`) run.
6. Update `docs/webapi.md`, `docs/workflow.md`, `docs/scripts.md`.


## Acceptance criteria

- [x] Test: a build list over 64 KB → 200; custom data without `compiles`; `compile-list.json` in the meta directory contains it.
- [x] Test: the custom data beside `compiles` is still limited to 64 KB.
- [x] Test: `compiles` which isn't a list → 422, no deployment created.
- [x] Test: compile list over `C_MAX_COMPILE_LIST_SIZE` → 422.
- [x] Test: `get_compile_list()` of an older deployment returns `custom_data.compiles`.
- [x] Test: `create_fields` doesn't have to list `compiles`.
- [x] Test: the hook `deployment_created` can read the compile list.


## Non-goals

* Show the compile list in the web app or the Web API.
* Move the compile lists of existing deployments out of their custom data (they keep working through the fallback).
* `GET /api/start_workflow/{wf_name}`: query parameters are text, `compiles` stays custom data there.


## Decisions

* Separate endpoint or field in `start_workflow`? **Field `compiles` in `start_workflow`, so OBI 1.5.3 keeps working.**
* Storage? **File `compile-list.json` in the meta directory of the deployment (next to the sources `obi.py` copies to `src/`). No database change. Written before the deployment is saved; the version number is reserved before, so the directory is unique.**
* Which workflows may get a compile list? **Every workflow.** Its values end up in the properties of deploy objects and in commands, and `obi.py` copies the files of `absolute_path`. So it's user input like custom data, see [installation](../installation.md#production-checklist).
* Size limit? **`C_MAX_COMPILE_LIST_SIZE`, 32 MB by default.** The command logs aren't part of it.
* Existing deployments? **No data is changed, `get_compile_list()` falls back to `custom_data.compiles`.**


## Open questions

* Deployments with a compile list in custom data over 64 KB still can't be edited. Allow edits which don't make the custom data larger?
