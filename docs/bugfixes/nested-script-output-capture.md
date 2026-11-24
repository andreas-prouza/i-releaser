# A SCRIPT step which runs a SCRIPT sub-step breaks the output of the process

- **Status:** finished (2026-11-23; tested with `tests/test_review_2026_11_modules.py`)
- **Type:** bug
- **Priority:** P2
- **Found:** 2026-11-23, reproduced


## Current situation

`output_capture.capture` ([output_capture.py:67](../../modules/output_capture.py#L67)) collects stdout and stderr of a thread for a `SCRIPT` step.
It keeps one buffer per thread id ([output_capture.py:83](../../modules/output_capture.py#L83)).

If a script runs a sub-step of type `SCRIPT` in the same thread (`IBM_i_commands(mf).execute_action(...)` with a `SCRIPT` action which isn't parallel), the captures are nested:

1. The inner capture replaces the buffer of the outer one and deletes it at its end.
2. The output of the outer step after the sub-step goes to the real stdout (the log of the web app or service), not to the step.
3. The outer `del sys.stdout.buffers[thread_id]` ([output_capture.py:90](../../modules/output_capture.py#L90)) raises `KeyError`: the step fails, `_uninstall` isn't called, `sys.stdout`/`sys.stderr` stay replaced for the whole process, and the log handler of the outer capture is never removed (it keeps writing into a closed `StringIO`).

Reproduced:

```python
with output_capture.capture(a, b):
    print('outer')
    with output_capture.capture(io.StringIO(), io.StringIO()):
        print('inner')
    print('outer again')        # goes to the real stdout
# KeyError: <thread id>, sys.stdout is still replaced
```

The example scripts only run `QSYS`/`PASE` sub-steps, so they aren't affected. Own scripts which run `SCRIPT` sub-steps are.


## Requirements

1. Captures can be nested in a thread: each thread has a stack of buffers. The innermost one gets the output; at its end the outer one is active again.
2. The log handler of a capture only takes the records while its capture is the innermost one of the thread.
3. An exception inside a capture never leaves `sys.stdout`/`sys.stderr` replaced (cleanup in `finally`, in the right order).


## Acceptance criteria

- [x] Test (the reproduction above): `outer` and `outer again` are in the outer buffer, `inner` only in the inner one, no exception, `sys.stdout` is restored.
- [x] Test: log records go to the innermost capture; an exception restores the streams.
- [x] Test: a `SCRIPT` step which runs a `SCRIPT` sub-step: both steps have their own output (`tests/test_commands.py`).


## Open questions

* None.
