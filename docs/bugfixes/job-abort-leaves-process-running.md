# A job without heartbeat is set to failed, but its process keeps running

- **Status:** ready (implemented 2026-11-24, tested with `tests/test_processing_service.py`, class `TestHangingJobProcess`. Open: `lockf` of a job and `killpg` checked on an IBM i)
- **Type:** bug
- **Priority:** P2
- **Found:** 2026-11-23, code review


## Current situation

`recover_orphans` ([processing_service.py:301](../../modules/processing_service.py#L301)) aborts a running job if its process doesn't exist anymore, or if it hasn't sent a heartbeat for `C_SERVICE_HEARTBEAT_TIMEOUT` seconds (60).
In the second case the process may still be alive. The code assumes the pid has been reused by another process, but a job can also miss its heartbeat because:

* the database is locked for a long time (the heartbeat waits up to 30 seconds per attempt),
* the system is very busy, or the job process is held (e.g. `HLDJOB` of the PASE job).

`abort_job` ([processing_service.py:264](../../modules/processing_service.py#L264)) then sets the job, the stage and the deployment to `failed` and runs the hook `STAGE_FAILED`, **without ending the process**.
The process keeps running its steps:

* it saves its stage and steps over the `failed` status,
* at its end `finish_job` writes its own status, without condition ([processing_job_data.py:182](../../modules/db/processing_job_data.py#L182)),
* a user may already have started the stage again (it was `failed`), so two runs of the same stage are active.

Hooks also run in the main loop of the service ([processing_service.py:296](../../modules/processing_service.py#L296)): a slow hook (e.g. Jira) delays all other jobs, and a hook which starts threads makes the next `os.fork()` unsafe.


## Requirements

1. Before a job without heartbeat is aborted, the service checks whether the pid is still its process (e.g. compare the start time of the process stored with the job; on PASE `ps -o etime=`/`lstart`).
   * Same process: end its process group (`SIGTERM`, after 10 seconds `SIGKILL`), then abort.
   * Other process: abort (as today).
2. `finish_job` only changes a job in status `running` (`WHERE id = ? AND status = 'running'`). A job which was aborted keeps `failed` and the reason.
3. A job process checks before each step whether its job is still `running`. If not, it stops without changing the stage.
4. Hooks of `abort_job` run in a thread or in their own process, not in the main loop.
5. The heartbeat uses a short busy timeout (e.g. 5 seconds) and tries again at the next interval, so a locked database doesn't make it miss a whole timeout.


## Acceptance criteria

- [x] Test: a job process which is alive but sends no heartbeat (simulated) is ended before the job is set to `failed`.
- [x] Test: `finish_job` after an abort doesn't change the job.
- [x] Test: a job whose status is changed to `failed` by someone else ends after its current step and doesn't change the stage.
- [x] Test: a hook which sleeps 5 seconds in `abort_job` doesn't delay the start of the next job.


## Decisions (2026-11-24)

* Requirement 1: the process of a job holds a lock of its job (`var/jobs/{id}.lock`, `lockf` like the lock of the service) instead of comparing start times: `ps` differs between Linux and PASE. If the lock is held, the pid is still the process of the job and it's ended (`SIGTERM`, then `SIGKILL`, its process group).
* Requirement 3: `processing_job.check_job_running` before each step; a job is ended if its status is `finished`, `failed` or `canceled`.
* `finish_job` only changes a job which hasn't ended (`queued` or `running`).
* Requirement 5: the heartbeat waits at most 5 seconds for a locked database (`get_db_connection(timeout=…)`) and is tried again at the next interval.
* A finished stage is refused by the transition if the stage has been set to `failed` meanwhile ([core redesign](../features/core-redesign.md), step 1): the next stages aren't activated.


## Open questions

* None.
