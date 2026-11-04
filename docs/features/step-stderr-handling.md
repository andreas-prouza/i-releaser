# Configurable error handling for output on stderr

- **Status:** finished
- **Type:** improvement
- **Priority:** P3


## Current situation

A `PASE` or `QSYS` step fails if its exit code isn't 0 **or** if it writes anything to stderr ([ibm_i_commands.py:251](../../modules/ibm_i_commands.py#L251)).

Many tools write warnings or progress to stderr although they worked, e.g.:

* `ssh`/`scp`: `Warning: Permanently added 'host' to the list of known hosts.`
* `git`: progress messages of `clone`, `push`, `checkout`

Users have to add `2>&1` or turn off the error check, which hides real errors.


## Requirements

1. Step actions get an option, e.g. `fail_on_stderr` (`true`/`false`).
2. The default keeps today's behavior (`true`), so existing workflows don't change.
3. With `false` only the exit code decides. stderr is still stored and shown.
4. Document it in `docs/workflow.md#step-actions` and `docs/concepts.md`.


## Acceptance criteria

- [x] Test: `echo warn >&2; exit 0` with `fail_on_stderr: false` → `finished`, stderr stored.
- [x] Test: the same without the option → `failed` (as today).
- [x] Test: `exit 1` with `fail_on_stderr: false` → `failed`.
- [x] `Workflow.validate_workflow` accepts the new attribute.


## Non-goals

* Parsing the output for errors


## Decisions

* Also per stage or workflow? **Only per step.**
