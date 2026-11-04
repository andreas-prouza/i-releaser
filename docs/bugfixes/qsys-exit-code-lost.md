# The exit code of a QSYS command gets lost

- **Status:** ready (Implemented. Open: the check on a real IBM i, see below.)
- **Type:** bug
- **Priority:** P2
- **Found:** 2026-11-01, reproduced with a simulated `cl`


## Current situation

A `QSYS` step runs `(cl -v '<command>'; cl -v "dspjoblog")` ([ibm_i_commands.py](../../modules/ibm_i_commands.py)). Its exit code is the one of `dspjoblog`, so the exit code of the command got lost.

A failed command was only noticed through its output on stderr:

* With `fail_on_stderr: false` a failed `QSYS` step was `finished`, although [the documentation](../workflow.md#step-actions) says the exit code decides.
* With the default it was `finished` too, if `cl` wrote nothing to stderr. That's probably rare: `scripts/obi.py` hides the output of expected errors with `2> /dev/null`, so `cl` seems to write them to stderr. It's not confirmed on an IBM i.

Reproduction: a `cl` which ends with exit code 1 and without output on stderr → the step is `finished`.


## Requirements

1. The exit code of the command decides if a `QSYS` step failed, also over SSH.
2. The job log stays part of the output, also after a failed command.
3. A failed `dspjoblog` doesn't fail a step.


## Acceptance criteria

- [x] Test: a failed command without output on stderr → `failed`, with and without `fail_on_stderr`.
- [x] Test: the same over SSH.
- [x] Test: the job log of a failed command is stored.
- [x] Test: `dspjoblog` fails, the command doesn't → `finished`.
- [x] On an IBM i: a failed command has an exit code other than 0 (`DLTF` of a missing file: `rc=-1`).
- [ ] On an IBM i: a successful command has the exit code 0.


## Non-goals

* Parsing the output for errors


## Decisions

* The last part of the command is `[ "$rc" -eq 0 ]` and not `exit $rc`: the shell on IBM i reported `-1`, and not every shell accepts that for `exit`. The step only needs to know whether the command failed.
