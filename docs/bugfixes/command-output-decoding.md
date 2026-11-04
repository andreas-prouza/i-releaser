# Command output which isn't UTF-8 fails the step and is lost

- **Status:** finished
- **Type:** bug
- **Priority:** P2
- **Found:** 2026-10-23, code review


## Current situation

`run_pase_cmd` decodes stdout and stderr strictly as UTF-8 ([ibm_i_commands.py:241](../../modules/ibm_i_commands.py#L241)).
If a command writes a byte which isn't valid UTF-8 (e.g. `ä` in ISO-8859-1 / CCSID 819, common in job logs and spool files on IBM i):

* `UnicodeDecodeError` is raised, the step is `failed`, although the command may have worked;
* the stored error is the decoding error, the real output of the command is lost.

The same applies to `QSYS` commands, which run through `run_pase_cmd`.


## Requirements

1. The output is always stored. Bytes which can't be decoded are replaced (`errors='replace'`), or decoded with a configurable fallback encoding.
2. The status of the step only depends on exit code and stderr (as documented), not on the decoding.
3. Optional: the encoding is configurable per system (e.g. in `etc/constants.py`).


## Acceptance criteria

- [x] Unit test: a command which prints `b'\xe4'` and exits with 0 → step `finished`, output contains the replacement (or `ä` with the fallback encoding).
- [x] Unit test: a command which prints invalid bytes to stderr and exits with 1 → step `failed`, stderr stored.


## Non-goals

* [Timeouts of commands](../features/command-timeout.md)


## Decisions

* Fallback encoding or replace? **Replace invalid bytes (`errors='replace'`).**
