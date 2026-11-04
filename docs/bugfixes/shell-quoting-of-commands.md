# QSYS and remote commands are changed by the shell

- **Status:** ready (Implemented. Open: the check on IBM i.)
- **Type:** security / bug
- **Priority:** P1
- **Found:** 2026-10-23, reproduced
- **Confidential:** don't publish before the fix is released


## Current situation

`QSYS` commands are run with bash as `cl -v "<command>"` ([ibm_i_commands.py:202](../../modules/ibm_i_commands.py#L202)).
Inside double quotes bash still replaces `$NAME`, `${...}`, `$(...)` and backticks:

```
CRTDUPOBJ OBJ($ORDERS) FROMLIB(PROD) OBJTYPE(*FILE) NEWOBJ(#ORD`date +%s`)
→ cl gets: CRTDUPOBJ OBJ() FROMLIB(PROD) OBJTYPE(*FILE) NEWOBJ(#ORD1792777090)
```

* Object names with `$` are common on IBM i: such commands silently work on the wrong object, or fail.
* Backticks and `$(...)` run on the local system, also for remote commands.
* A `"` in the command ends the quoting.

Remote commands are wrapped as `ssh "<host>" "<command>"`, only `"` is escaped ([ibm_i_commands.py:196](../../modules/ibm_i_commands.py#L196)).
The remote shell parses the command again.

`scripts/examples/target_deployment.py` works around it with `name.replace('$', '\\$')` in one place.


## Requirements

1. The text of a `QSYS` command reaches `cl` unchanged, whatever characters it contains (`$ # @ " ' \` and backticks). Use `shlex.quote`.
2. Remote commands: host and command are quoted for the local and for the remote shell, so the command reaches `cl` on the target unchanged too.
3. `PASE` commands stay shell commands (no change).
4. Remove the workaround in `target_deployment.py`.


## Acceptance criteria

- [x] Unit test: `cl` replaced by a stub which writes its arguments → commands with `$`, `#`, `@`, `"`, `'`, `\` and backticks arrive unchanged.
- [x] Unit test: the same through `ssh` (stub which runs the command with `sh -c`).
- [ ] Checked on IBM i: `CRTDTAARA DTAARA(QTEMP/$TEST) TYPE(*CHAR)` creates `$TEST`.


## Non-goals

* [Placeholders with user input](command-placeholders-with-user-input.md)


## Decisions

* Shell of the SSH users? **No decision needed: single quotes work in all POSIX shells.**
