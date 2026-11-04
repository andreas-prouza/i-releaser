# Command placeholders: user input in shell commands, and braces break commands

- **Status:** finished
- **Type:** security / bug
- **Priority:** P1
- **Found:** 2026-10-23, code review
- **Confidential:** don't publish before the fix is released


## Current situation

If a command contains `{` or `}`, it's filled in with Python's `str.format` and the whole deployment as values ([ibm_i_commands.py:90](../../modules/ibm_i_commands.py#L90)).
`PASE` and `QSYS` commands then run with `shell=True`.

* **Injection:** if a command uses custom data (`{meta_file[custom_data][ticket]}`), the value comes from users with `start workflow` or `edit-custom-data`.
  A value like `x; rm -rf ~` runs as shell command under the user profile of i-Releaser.
* **Broken commands:** every brace is a placeholder. `awk '{print $1}'` or `echo ${HOME}` fail with `KeyError`; users have to write `{{` and `}}`.
* `str.format` also allows attribute access in the template (`{meta_file.__class__}`). The templates come from administrators, so this is only a hardening point.


## Requirements

1. Only known placeholders are replaced: `{stage}`, `{processing_step}`, `{meta_file[...]}`. Other braces stay unchanged (no `KeyError`).
2. Values which are inserted into `PASE` commands are shell-quoted. Values in `QSYS` commands are quoted as CL strings, or rejected if they contain characters which aren't allowed.
3. Placeholders are resolved by an own resolver (dict keys and list indexes only), not by `str.format`.
4. Existing commands with `{{` and `}}` keep working (or the changelog explains the migration).
5. Update `docs/workflow.md#placeholders`.


## Acceptance criteria

- [x] Unit test: `awk '{print $1}'` and `echo ${HOME}` run unchanged.
- [x] Unit test: custom data `x; touch /tmp/pwned` in a `PASE` command placeholder → the file isn't created; the value is passed as one argument.
- [x] Unit test: a `QSYS` command placeholder with `'` in the value results in a valid, quoted CL string.
- [x] Unit test: `{meta_file.__class__}` isn't resolved.


## Non-goals

* [Quoting of the whole QSYS command](shell-quoting-of-commands.md)


## Decisions

* Custom data in command placeholders at all? **Yes, but always quoted (`PASE`) or checked (`QSYS`).**
* How to handle values in `QSYS` commands? **Reject values with characters other than letters, digits, `$ # @ _ . / -`: the step fails with a message. Quoting can't work, because a value may be inside or outside a CL string.**
