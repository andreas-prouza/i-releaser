# Remove dead code and unused files

- **Status:** finished
- **Type:** improvement
- **Priority:** P3


## Current situation

Code and files which aren't used anymore, or don't work:

| What | Where | Note |
|---|---|---|
| `Meta_File.__eq__` | [meta_file.py:891](../../modules/meta_file.py#L891) | Broken: compares `s.commit` with itself, calls `get_deploy_objects` which doesn't exist |
| `Meta_File.is_backup_name_already_in_use` | [meta_file.py:661](../../modules/meta_file.py#L661) | Unused, written for the old JSON meta files |
| `Meta_File.import_objects_from_config_file_old`, `add_object_from_meta_structure` | [meta_file.py:905](../../modules/meta_file.py#L905) | Unused |
| `Workflow.get_scripts` | [workflow.py:313](../../modules/workflow.py#L313) | Unused, reads keys which don't exist |
| `flowchart.get_flowchart_text` | [flowchart.py:267](../../webapp/web_modules/flowchart.py#L267) | Unused, uses `mf.actions` which doesn't exist |
| `show_json` in the deployment page | `webapp/templates/overview/show-deployment.html` | Unused, calls a URL which doesn't exist |
| `list-deployments copy.html` | `webapp/templates/overview/` | Copy of a template |
| `build.run_compile_script`, `gen_commands.generate_commands` | `scripts/examples/` | Marked deprecated, can't be called (see [templates](../bugfixes/example-scripts-and-configs.md)) |
| `C_STAGE_COMMANDS`, `stage_commands.json` | `etc/constants.py`, `etc/examples/` | Not read anywhere |
| `flask_config.py` | `webapp/etc/examples/` | From the time of Flask |
| starsessions | `initial.py`, `webmiddleware.py` | See [session handling](../bugfixes/session-store-hardening.md) |


## Requirements

1. Remove the code and files above, unless a test shows they are needed.
2. Decide about the old workflow file `etc/workflow.json` (deprecated): keep the support or remove it in a later version (see open questions).
3. Remove what the decision about the [command line](../bugfixes/cli-deployment-py-broken.md) makes obsolete.
4. Changelog entry for removed templates.


## Acceptance criteria

- [x] All tests pass.
- [x] `grep` finds no references to the removed functions and files.
- [x] Web app and processing service start, and a workflow runs.


## Non-goals

* Refactoring of code which is used


## Decisions

* When to remove `etc/workflow.json`? **Keep the support now, remove it in the next major version.**
