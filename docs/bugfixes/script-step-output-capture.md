# SCRIPT steps capture the output of the whole process

- **Status:** finished
- **Type:** bug
- **Priority:** P2
- **Found:** 2026-10-23, code review


## Current situation

To store the output of a `SCRIPT` step, `run_script_cmd` ([ibm_i_commands.py:132](../../modules/ibm_i_commands.py#L132)):

* adds a log handler to the root logger, without a filter for the thread;
* replaces `sys.stdout` and `sys.stderr` of the whole process (`redirect_stdout`, `redirect_stderr`);
* sets the level of the root logger to `DEBUG` and restores it at the end.

In thread mode several stages and all web requests run in the same process. So:

* log entries and prints of other stages and requests (also of other deployments) end up in the log of the step;
* two scripts at the same time restore `sys.stdout` in the wrong order. `sys.stdout` can be left pointing to a closed buffer, and every later `print` fails with `ValueError: I/O operation on closed file`;
* the root logger can stay at `DEBUG` (the second script restores the level the first one had set). See also [session takeover via logs](session-takeover-via-logs.md).

With the processing service each job has its own process, so only thread mode is affected.


## Requirements

1. The log of a step contains only the output of that step (log entries and prints of its thread).
2. `sys.stdout` and `sys.stderr` stay usable for all other threads, also when several scripts run at the same time.
3. The level of the root logger isn't changed. The step's handler gets its own level.


## Acceptance criteria

- [x] Test: two `SCRIPT` steps run in parallel threads, each prints and logs its own text 1000 times → each step log contains only its own lines.
- [x] Test: after both have ended, `print` works and the root log level is unchanged.
- [x] Test: log entries of a web request during a step don't appear in the step log.


## Non-goals

* Changes for the processing service
