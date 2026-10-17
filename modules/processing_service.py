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

import logging
import os
import select
import signal
import socket
import threading
import time

from etc import constants
# Before meta_file (circular import)
from modules import deploy_version
from modules import files, hooks, meta_file, stage_status
from modules.db import meta_file_data, processing_job_data
from modules.job_status import Status as Job_Status
from modules.meta_file_status import Meta_file_status
from modules.processing_job import Processing_Job



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
    raise Exception(f"Processing job {job_id} not found")

  logging.info(f"Run processing job {job.id}: {job.meta_file_id=}, {job.stage_id=}, {job.processing_step=}, {job.continue_run=}, {job.user=}")

  processing_job_data.set_job_pid(job.id, os.getpid())
  meta_file.Meta_File.CURRENT_USER = job.user

  stop_heartbeat = threading.Event()
  heartbeat = threading.Thread(target=send_heartbeats, args=(job.id, stop_heartbeat), daemon=True)
  heartbeat.start()

  status = Job_Status.FINISHED
  error = None

  try:
    mf = meta_file_data.get_meta_file_by_id(job.meta_file_id)
    if mf is None:
      raise Exception(f"Meta file for ID {job.meta_file_id} not found")

    mf.run_current_stage(job.stage_id, job.processing_step, job.continue_run)

  except BaseException as e:
    logging.exception(e, stack_info=True)
    status = Job_Status.FAILED
    error = get_error_text(e)

    if not isinstance(e, Exception):
      raise

  finally:
    stop_heartbeat.set()
    heartbeat.join()
    processing_job_data.finish_job(job.id, status, error)

  return status



def is_process_running(pid: int) -> bool:

  try:
    os.kill(pid, 0)
  except ProcessLookupError:
    return False
  except PermissionError:
    # It exists, but belongs to another user
    return True

  return True



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

  for stage in failed_stages:
    hooks.emit(hooks.Event.STAGE_FAILED, mf, stage)



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
      # Most likely the pid is used by another process meanwhile
      error = f"No sign of life from job process {job.pid} for more than {constants.C_SERVICE_HEARTBEAT_TIMEOUT} seconds"

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
    # {pid: job id} of the job processes which have been started by this service
    self.children: dict[int, int] = {}
    self.stop_requested: bool = False



  def start(self) -> None:

    if notify():
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

    running_jobs = processing_job_data.get_jobs(status=[Job_Status.RUNNING])
    logging.info(f"Processing service stopped. Jobs which are still running: {[job.id for job in running_jobs]}")



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

      if run_job(job.id) == Job_Status.FINISHED:
        exit_code = 0

      # The service may start the next job of its queue
      notify()

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
