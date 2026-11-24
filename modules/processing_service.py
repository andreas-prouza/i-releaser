"""
Processing service

Runs stages independent of the web app, so a stage keeps running if the web app ends.

  web app                                      processing service (serviceapp/service.py)

  Meta_File.start_stage()
    job in table processing_jobs (queued)
    notify()  ---------- wake up ---------->   Service.run_once()
                                                 claims the job (running)
                                                 fork: run_job() runs the stage in its own process

The database is the only interface between both. The wake up only avoids waiting for the next look into the queue.
See docs/processing-service.md
"""
from __future__ import annotations

import datetime
import errno
import fcntl
import logging
import os
import select
import signal
import socket
import threading
import time

from etc import constants
# Before meta_file (circular import)
from modules import action_type, current_user, errors, files, hooks, notifications, stage_status
from modules.db import meta_file_data, processing_job_data, processing_user_data
from modules.job_status import Status as Job_Status
from modules.meta_file_status import Meta_file_status
from modules import processing_job
from modules.processing_job import Processing_Job, format_utc_text, utc_now



# Characters of an error which are stored for a job. The complete error is in the logs of the stage.
MAX_ERROR_LENGTH = 2000



class ServiceAlreadyRunningException(Exception):
    pass



def get_socket_address() -> str:
    """
    The path of a unix socket is limited to about 100 characters.
    So the relative path is used, if it's shorter (e.g. '../var/processing-service.sock' for the web app and the service).
    """

    relative_path = os.path.relpath(constants.C_SERVICE_SOCKET)
    return relative_path if len(relative_path) < len(constants.C_SERVICE_SOCKET) else constants.C_SERVICE_SOCKET



def try_lock(lock_file: str):
    """
    Exclusive lock of the given file, without waiting.

    A POSIX record lock (lockf), which is available in PASE too. It belongs to the process:
    a forked job process doesn't hold it, and it's released when the process ends.

    Returns:
        The open file, which holds the lock until it's closed. None if another process holds it.
    """

    os.makedirs(os.path.dirname(lock_file), exist_ok=True)
    # 'a': an exclusive lock needs write access, and the file is not truncated
    f = open(lock_file, 'a')

    try:
        fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)

    except OSError as e:
        f.close()
        if e.errno in (errno.EACCES, errno.EAGAIN):
            return None
        raise

    return f



def notify() -> bool:
    """
    Wakes up the processing service, so it looks into its queue immediately.

    Returns:
        bool: False if the processing service is not running
    """

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.setblocking(False)
            s.sendto(b'1', get_socket_address())

    except BlockingIOError:
        # It's listening, but has not processed the previous wake ups yet
        return True

    except OSError as e:
        logging.debug(f"Processing service is not listening on {constants.C_SERVICE_SOCKET}: {e}")
        return False

    return True



def send_heartbeats(job_id: int, stop: threading.Event) -> None:
    """Sign of life of a running job, so the service knows that its process still exists"""

    while not stop.wait(constants.C_SERVICE_HEARTBEAT_INTERVAL):
        try:
            processing_job_data.touch_heartbeat(job_id)
        except Exception as e:
            logging.warning(f"Could not update heartbeat of processing job {job_id}: {e}")



def get_error_text(e: BaseException) -> str:

    error = str(e) or type(e).__name__

    # A failed step raises the reference to its error log instead of the error itself
    if error.startswith('file://'):
        try:
            error = files.readFile(error.removeprefix('file://'))
        except OSError:
            pass

    return error[:MAX_ERROR_LENGTH]



def run_job(job_id: int) -> Job_Status:
    """
    Runs the stage of the given job in the current process, in the name of the user who started it.

    Returns:
        Job_Status: Final status of the job
    """

    job = processing_job_data.get_job(job_id)
    if job is None:
        raise errors.Not_Found_Error(f"Processing job {job_id} not found")

    logging.info(f"Run processing job {job.id}: {job.meta_file_id=}, {job.stage_id=}, {job.processing_step=}, {job.continue_run=}, {job.user=}")

    processing_job_data.set_job_pid(job.id, os.getpid())
    current_user.set_user(job.user)
    # Each step checks that the job is still running (IBM_i_commands._run_action)
    job_token = processing_job.current_job_id.set(job.id)

    stop_heartbeat = threading.Event()
    heartbeat = threading.Thread(target=send_heartbeats, args=(job.id, stop_heartbeat), daemon=True)
    heartbeat.start()

    status = Job_Status.FINISHED
    error = None
    mf = None
    # A run which didn't start (scheduled run or missing permission): reported after the job got its error
    not_run = False

    try:
        mf = meta_file_data.get_meta_file_by_id(job.meta_file_id)
        if mf is None:
            raise Exception(f"Meta file for ID {job.meta_file_id} not found")

        claimed = False

        # The user may have lost the permission since the run was queued or scheduled (docs/bugfixes/scheduled-run-without-permission-check.md)
        permission_error = get_permission_error(job, mf)

        if permission_error is not None:
            error = permission_error
            not_run = True

        elif job.is_scheduled():
            error = start_scheduled_run(job, mf)
            not_run = error is not None
            error = error[:MAX_ERROR_LENGTH] if error else None
            claimed = not not_run

        if not_run:
            status = Job_Status.FAILED
        else:
            mf.run_current_stage(job.stage_id, job.processing_step, job.continue_run, claimed=claimed)

    except BaseException as e:
        logging.exception(e, stack_info=True)
        status = Job_Status.FAILED
        error = get_error_text(e)

        if not isinstance(e, Exception):
            raise

    finally:
        stop_heartbeat.set()
        heartbeat.join()
        processing_job.current_job_id.reset(job_token)
        processing_job_data.finish_job(job.id, status, error)

    if not_run:
        if job.is_scheduled():
            report_failed_scheduled_run(job, mf, error)
        else:
            report_not_run(job, mf, error)

    return status



def get_permission_error(job: Processing_Job, mf) -> str|None:
    """
    Returns:
        str|None: Why the user of the job may not run its stage anymore, None if it may
    """

    # Here: permission_config imports the data modules, which import this module's modules
    from modules import permission_config, permissions

    stage = mf.get_stage_by_id(job.stage_id)
    stage_name = stage.name if stage else None

    if permission_config.is_user_allowed(job.user, permissions.PermissionAction.RUN_WORKFLOW, mf.workflow.name, stage_name, job.stage_id):
        return None

    return f"User {job.user} has no permission 'run' for stage {stage_name or job.stage_id} anymore. The stage has not been run."



def report_not_run(job: Processing_Job, mf, error: str) -> None:
    """History entry for a queued run which didn't start"""

    logging.warning(f"Job {job.id} didn't start: {error}")

    try:
        processing_user_data.create_action_log(action_type.Action_type.RUN_STAGE, details=f"Not run (job {job.id}): {error}",
                                               meta_file=mf, stage=mf.get_stage_by_id(job.stage_id))
    except Exception as e:
        logging.exception(e, stack_info=True)



def start_scheduled_run(job: Processing_Job, mf) -> str|None:
    """
    Checks a scheduled run when its time has come (docs/features/scheduled-stage-run.md) and claims its stage.

    Returns:
        str|None: Why it can't be run (the stage is not touched). None: the stage is claimed (`in process`) and can be run.
    """

    delay = utc_now() - job.run_at
    limit = constants.C_SCHEDULE_MAX_DELAY_MINUTES

    # 0: no limit. The time itself is not part of the text: it's shown by the web app in the time zone of the browser.
    if limit and delay > datetime.timedelta(minutes=limit):
        return (f"Missed the scheduled time by {int(delay.total_seconds() // 60)} minutes (limit C_SCHEDULE_MAX_DELAY_MINUTES = {limit}), "
                f"e.g. because the processing service wasn't running. The stage has not been run.")

    try:
        mf.check_deployment_ready_2_run(stage_id=job.stage_id, processing_step=job.processing_step)
        mf.claim_stage(job.stage_id)

    except Exception as e:
        return f"The stage could not be run: {e}"

    mf.run_details[job.stage_id] = f"Scheduled run for {format_utc_text(job.run_at)} (job {job.id})"
    return None



def report_failed_scheduled_run(job: Processing_Job, mf, error: str) -> None:
    """History entry and hook `scheduled_run_failed`. The hook finds the reason in the error of the job."""

    logging.warning(f"Scheduled run of job {job.id} didn't start: {error}")

    try:
        stage = mf.get_stage_by_id(job.stage_id)
        processing_user_data.create_action_log(action_type.Action_type.SCHEDULED_RUN_FAILED, details=f"Scheduled for {format_utc_text(job.run_at)} (job {job.id}): {error}",
                                               meta_file=mf, stage=stage)
        hooks.emit(hooks.Event.SCHEDULED_RUN_FAILED, mf, stage, details=f"Scheduled for {format_utc_text(job.run_at)}: {error}")

    except Exception as e:
        logging.exception(e, stack_info=True)



def is_process_running(pid: int) -> bool:

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # It exists, but belongs to another user
        return True

    return True



def get_start() -> tuple[datetime.datetime, int|None] | None:
    """
    Start of the processing service in UTC and its process id, from its pid file (docs/features/start-times.md).
    The file is written at the start. It's only valid while the service runs: a killed service leaves it behind.
    """

    try:
        started = os.path.getmtime(constants.C_SERVICE_PID_FILE)
        with open(constants.C_SERVICE_PID_FILE) as f:
            content = f.read().strip()
    except OSError:
        return None

    return datetime.datetime.fromtimestamp(started, datetime.timezone.utc).replace(microsecond=0), int(content) if content.isdigit() else None



def get_job_lock_file(job_id: int) -> str:
    return os.path.join(os.path.dirname(constants.C_SERVICE_LOCK_FILE), 'jobs', f"{job_id}.lock")



def is_job_process(job: Processing_Job) -> bool:
    """The process of the job is still running: it holds the lock of its job (another process with the same pid doesn't)"""

    lock = try_lock(get_job_lock_file(job.id))

    if lock is None:
        return True

    lock.close()
    return False



def end_job_process(job: Processing_Job, wait_seconds: float=10) -> None:
    """Ends the process of a job with its commands (own process group, see run_job_process): SIGTERM, then SIGKILL"""

    for sig in [signal.SIGTERM, signal.SIGKILL]:
        try:
            os.killpg(job.pid, sig)
        except (ProcessLookupError, PermissionError):
            return

        end = time.time() + wait_seconds
        while time.time() < end:
            if has_ended(job.pid):
                return
            time.sleep(0.2)



def has_ended(pid: int) -> bool:
    """Also for a child of this process which has ended but hasn't been reaped yet (it would still exist)"""

    try:
        if os.waitpid(pid, os.WNOHANG)[0] == pid:
            return True
    except ChildProcessError:
        # Not a child of this process: it's reaped by its parent
        pass

    return not is_process_running(pid)



def abort_job(job: Processing_Job, error: str) -> None:
    """
    Sets a job whose process doesn't exist anymore to failed. Including the stage it was running,
    so the stage can be run again.
    """

    logging.error(f"Processing job {job.id} aborted: {error}")
    processing_job_data.finish_job(job.id, Job_Status.FAILED, error)

    mf = meta_file_data.get_meta_file_by_id(job.meta_file_id)
    if mf is None:
        return

    other_jobs = processing_job_data.get_jobs(status=[Job_Status.RUNNING], meta_file_id=mf.id)
    failed_stages = []

    for stage in mf.get_open_stages():

        if stage.status != stage_status.Status.IN_PROCESS:
            continue

        # The job may have been running a following stage (run_immediate).
        # But it can't be told from the stages of the other running jobs of this deployment.
        if len(other_jobs) > 0 and stage.id != job.stage_id:
            continue

        stage.set_status(stage_status.Status.FAILED)
        failed_stages.append(stage)

    if len(other_jobs) == 0 and mf.status == Meta_file_status.IN_PROCESS:
        mf.set_status(Meta_file_status.FAILED)

    # In a thread: a slow hook (e.g. Jira) must not delay the jobs of the service
    if failed_stages:
        def emit_failed() -> None:
            # The user who ran it, e.g. for the recipient @runner of the notifications
            current_user.set_user(job.user)
            for stage in failed_stages:
                hooks.emit(hooks.Event.STAGE_FAILED, mf, stage, details=f"The run has been aborted (job {job.id}): {error}")

        threading.Thread(target=emit_failed, daemon=True).start()



def recover_orphans() -> list[Processing_Job]:
    """
    Aborts running jobs whose process doesn't exist anymore (e.g. it has been killed or the system has been restarted).

    Returns:
        list[Processing_Job]: Aborted jobs
    """

    aborted = []

    for job in processing_job_data.get_jobs(status=[Job_Status.RUNNING]):

        has_heartbeat = job.heartbeat is not None and time.time() - job.heartbeat <= constants.C_SERVICE_HEARTBEAT_TIMEOUT

        if job.pid is None:
            # Claimed, its process is going to be started
            if has_heartbeat:
                continue
            error = "Job process has not been started"

        elif not is_process_running(job.pid):
            error = f"Job process {job.pid} doesn't exist anymore"

        elif not has_heartbeat:
            error = f"No sign of life from job process {job.pid} for more than {constants.C_SERVICE_HEARTBEAT_TIMEOUT} seconds"

            # Still its process (it hangs, or the database was locked): it must not go on after its job has been set to failed
            # (docs/bugfixes/job-abort-leaves-process-running.md). Otherwise the pid is used by another process meanwhile.
            if is_job_process(job):
                logging.warning(f"Job process {job.pid} of job {job.id} is ended: no sign of life")
                end_job_process(job)
                error += ". The process has been ended."

        else:
            continue

        abort_job(job, error)
        aborted.append(job)

    return aborted




class Service:
    """
    The processing service

    Waits for jobs in the queue and runs each of them in its own process (fork).
    So a job doesn't need to load python, the modules and the scripts first. And it's isolated from all other jobs.

    The service itself has only one thread and keeps no database connection open. That's necessary for a safe fork.
    """



    def __init__(self):

        self.socket: socket.socket|None = None
        # Open as long as the service runs (C_SERVICE_LOCK_FILE)
        self.lock = None
        # {pid: job id} of the job processes which have been started by this service
        self.children: dict[int, int] = {}
        self.stop_requested: bool = False



    def start(self) -> None:

        # Without the lock, two services started at the same time could both get past the check of the socket
        self.lock = try_lock(constants.C_SERVICE_LOCK_FILE)
        if self.lock is None:
            raise ServiceAlreadyRunningException(f"Processing service is already running ({constants.C_SERVICE_LOCK_FILE} is locked)")

        # A service of an older version, without the lock
        if notify():
            self.release_lock()
            raise ServiceAlreadyRunningException(f"Processing service is already running ({constants.C_SERVICE_SOCKET})")

        os.makedirs(os.path.dirname(constants.C_SERVICE_SOCKET), exist_ok=True)

        # Left over, if the service has been killed
        if os.path.exists(constants.C_SERVICE_SOCKET):
            os.remove(constants.C_SERVICE_SOCKET)

        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.bind(get_socket_address())
        self.socket.setblocking(False)

        files.writeText(str(os.getpid()), constants.C_SERVICE_PID_FILE)

        logging.info(f"Processing service started: pid {os.getpid()}, {constants.C_SERVICE_SOCKET=}")



    def stop(self) -> None:
        """Stops the service. Running jobs are not affected: they have their own process."""

        if self.socket is not None:
            self.socket.close()
            self.socket = None

        for file in [constants.C_SERVICE_SOCKET, constants.C_SERVICE_PID_FILE]:
            if os.path.exists(file):
                os.remove(file)

        # Released last: a new service may start now
        self.release_lock()

        running_jobs = processing_job_data.get_jobs(status=[Job_Status.RUNNING])
        logging.info(f"Processing service stopped. Jobs which are still running: {[job.id for job in running_jobs]}")



    def release_lock(self) -> None:
        """The lock file itself stays: removing it would allow a second lock on a new file"""

        if self.lock is not None:
            self.lock.close()
            self.lock = None



    def request_stop(self, signum=None, frame=None) -> None:

        logging.info(f"Stop of processing service requested ({signum=})")
        self.stop_requested = True
        # Don't wait for the next look into the queue
        notify()



    def wait_for_wakeup(self, timeout: float) -> None:

        readable, _, _ = select.select([self.socket], [], [], timeout)

        if not readable:
            return

        # One look into the queue is enough for all of them
        try:
            while True:
                self.socket.recv(16)
        except BlockingIOError:
            pass



    def reap_children(self) -> None:
        """Looks after the job processes which have ended"""

        for pid, job_id in list(self.children.items()):

            try:
                ended_pid, wait_status = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                ended_pid, wait_status = pid, None

            if ended_pid == 0:
                continue

            del self.children[pid]

            # A job process sets the final status by itself
            job = processing_job_data.get_job(job_id)
            if job is None or job.status != Job_Status.RUNNING:
                continue

            reason = ''
            if wait_status is not None:
                exit_code = os.waitstatus_to_exitcode(wait_status)
                reason = f" (signal {-exit_code})" if exit_code < 0 else f" (exit code {exit_code})"

            abort_job(job, f"Job process {pid} ended unexpectedly{reason}")



    def start_jobs(self) -> None:
        """Starts queued jobs, as long as C_SERVICE_MAX_PARALLEL_JOBS is not reached"""

        while len(processing_job_data.get_jobs(status=[Job_Status.RUNNING])) < constants.C_SERVICE_MAX_PARALLEL_JOBS:

            job = processing_job_data.claim_next_job()
            if job is None:
                return

            self.start_job_process(job)



    def start_job_process(self, job: Processing_Job) -> None:

        try:
            pid = os.fork()

        except OSError as e:
            logging.exception(e, stack_info=True)
            processing_job_data.finish_job(job.id, Job_Status.FAILED, f"Could not start job process: {e}")
            return

        if pid == 0:
            self.run_job_process(job)

        logging.info(f"Job process {pid} started for processing job {job.id}")
        self.children[pid] = job.id



    def run_job_process(self, job: Processing_Job) -> None:
        """The job process (child of the service): runs the job and ends. It never returns."""

        exit_code = 1

        try:
            # Own session: the job keeps running, if the service gets stopped
            os.setsid()
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            self.socket.close()
            # Only closes the copy of the job process: a lockf lock belongs to the service process
            if self.lock is not None:
                self.lock.close()

            # Tells the service that this process is the one of the job, also if its pid is checked later (recover_orphans)
            job_lock = try_lock(get_job_lock_file(job.id))  # noqa: F841 (open until the process ends)

            if run_job(job.id) == Job_Status.FINISHED:
                exit_code = 0

            # The service may start the next job of its queue
            notify()

            # The messages of the run, before the process ends (what fails is sent again by the web app)
            notifications.flush()

        except BaseException as e:
            logging.exception(e, stack_info=True)

        finally:
            logging.shutdown()
            # No clean up of the service: its socket and files are still in use
            os._exit(exit_code)



    def run_once(self, timeout: float|None=None) -> None:
        """
        One cycle of the service: wait for a wake up, look after the job processes and start the queued jobs

        Args:
            timeout (float, optional): Seconds to wait for a wake up. Defaults to C_SERVICE_POLL_INTERVAL
        """

        self.wait_for_wakeup(constants.C_SERVICE_POLL_INTERVAL if timeout is None else timeout)

        if self.stop_requested:
            return

        self.reap_children()
        recover_orphans()
        self.start_jobs()



    def run_forever(self) -> None:

        self.start()

        # No thread in the process which forks the jobs: the web app sends its notifications (docs/features/notifications.md)
        notifications.disable_sender()

        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)

        try:
            # Jobs which have been queued or lost their process while the service was not running
            timeout = 0

            while not self.stop_requested:
                try:
                    self.run_once(timeout)

                except Exception as e:
                    # E.g. a locked database. The next cycle tries again.
                    logging.exception(e, stack_info=True)

                timeout = None

        finally:
            self.stop()
