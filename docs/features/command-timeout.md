# Timeout for commands

- **Status:** finished
- **Type:** improvement
- **Priority:** P2


## Current situation

`PASE` and `QSYS` commands run without a timeout ([ibm_i_commands.py:236](../../modules/ibm_i_commands.py#L236)).
A command which waits forever blocks the stage:

* `ssh`/`scp` asking for a password or a host key confirmation;
* a CL command waiting for an answer to an inquiry message;
* a lock wait without limit.

In thread mode the stage stays `in process` until the web app is restarted; with the processing service until the job is killed.


## Requirements

1. Step actions get an option `timeout_seconds`. A global default is in the settings (e.g. 0 = no timeout, see open questions).
2. On timeout the command and its child processes are ended, the step is `failed`, and its log says `timeout after N seconds`.
3. Remote commands use `ssh -o BatchMode=yes`, so they fail instead of asking for a password.
4. `SCRIPT` steps: document that they can't be ended in thread mode. With the processing service, the job as a whole can have a timeout (see open questions).
5. Document it in `docs/workflow.md#step-actions`.


## Acceptance criteria

- [x] Test: `sleep 10` with `timeout_seconds: 1` → `failed` after about 1 second, the log says timeout, no `sleep` process is left.
- [x] Test: a command which ends in time isn't affected.
- [x] Test: the remote command contains `BatchMode=yes`.


## Non-goals

* Stopping a running stage from the web app


## Decisions

* Global default? **No timeout, as today.**
* Timeout for whole jobs? **Not now.**
