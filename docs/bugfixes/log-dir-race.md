# Processes which start at the same time can fail while creating the log directory

- **Status:** finished (2026-11-19; the test below passed 6 of 6 times after the fix, failed 1 of 3 before)
- **Type:** bug
- **Priority:** P3
- **Found:** 2026-11-19, flaky test `tests/test_service_auto_start.py::test_only_one_of_several_services_started_at_the_same_time`


## Current situation

Both logger templates create the log directory with "check, then create":

```python
if not Path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
```

If two processes start at the same time and the directory doesn't exist yet, both see it missing, and the second `makedirs` fails with `FileExistsError`. The process ends before it has logged anything.
This happens with several processing services started together (the test), and can happen with the gunicorn workers on the first start of a new installation.

Files: `etc/examples/logger_config.py`, `webapp/etc/examples/logger_config.py`.


## Requirements

1. The log directory is created with `os.makedirs(LOG_DIR, exist_ok=True)`.
2. Installations use their own copy in `etc/` and `webapp/etc/`: the changelog says which line to change.


## Acceptance criteria

- [x] The test passes repeatedly.
- [x] Changelog entry.


## Open questions

None.
