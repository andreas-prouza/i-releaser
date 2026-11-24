# JSON schema for workflow files

- **Status:** ready (implemented 2026-11-24, tested with `tests/test_workflow_schema.py`. Open: the check in VS Code by hand)
- **Type:** improvement
- **Priority:** P3
- **Source:** Code review 2026-11-23


## Current situation

* Workflows, step mappings and object commands are JSON files in `etc/` ([workflow configuration](../workflow.md)).
* They are checked when the web app reads them (`Workflow.validate_workflow`, [workflow.py:326](../../modules/workflow.py#L326)); an invalid file is listed on the workflow page.
* While writing a file there is no help: an unknown key (e.g. `run_imediate`) or a wrong type is only noticed in the web app, some not at all.
* `jsonschema` is in `requirements.txt` but not used (see [minor code defects](../bugfixes/minor-code-defects-2026-11.md)).


## Requirements

1. JSON schemas (draft 2020-12) in `docs/schema/`: `workflow.schema.json`, `step-mapping.schema.json` (`default_step_action.json`), `object-commands.schema.json`, `user-permissions.schema.json`.
2. Each key has a description (the text of [workflow.md](../workflow.md)), its type, allowed values (e.g. `environment`: `QSYS`, `PASE`, `SCRIPT`) and default; unknown keys are errors (`additionalProperties: false`) where the code refuses them too.
3. The examples in `etc/examples/` contain `"$schema": "../../docs/schema/workflow.schema.json"` (relative path). VS Code (and RDi with a JSON editor) then shows errors and completion. The code ignores the key `$schema`.
4. A test checks every example file and every workflow of the tests against the schema (with `jsonschema` as development package only, or a small own checker), and that the schema and `validate_workflow` agree on a list of invalid files.
5. The runtime check stays the one in Python (no new runtime package).


## Acceptance criteria

- [x] The examples are valid; a list of invalid workflows is refused by both the schema and `validate_workflow`.
- [ ] In VS Code, a misspelled key in an example shows an error (checked by hand).
- [x] `workflow.md` explains how to add `$schema` to own files.


## Non-goals

* An editor for workflows in the web app.


## Decisions (2026-11-24)

* The examples don't contain `$schema`: they are copied from `etc/examples/workflows/` to `etc/workflows/` (another depth), a relative path would be wrong after the copy. `workflow.md` shows the mapping in the settings of VS Code, which works for all files, also for the lists (`default_step_action.json`, `object_commands.json`), which can't contain `$schema`. A workflow file may contain `$schema`; the code ignores it.
* The schema of a stage only knows the attributes of a file, not the internal ones the code also accepts (`id`, `status`, `actions`, ...).
* `jsonschema` 4.17.3 as development package (review OK: 4,998 stars, 730 forks, MIT, checked 2026-11-24), only for the test.


## Open questions (answered 2026-11-24)

* `jsonschema` as development package (`requirements-dev.txt`) for the test, or an own small check? Proposal: development package (no runtime dependency, needs the [package review](../technik.md#package-prüfung); far above 200 stars).
