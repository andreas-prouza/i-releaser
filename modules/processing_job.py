import contextvars
import datetime

from modules import errors
from modules.job_status import Status as Job_Status




class Processing_Job:
  """
  Run of a stage which is processed by the processing service

  Parameters
  ----------
  user : str
    User who started the stage. The job is processed in the name of this user
  status : Job_Status
    * ``queued``: Waiting for the processing service (or for its time, see ``run_at``)
    * ``running``: A job process of the processing service runs the stage
    * ``finished``: The run of the stage has been finished successfully
    * ``failed``: The run of the stage failed or its job process ended unexpectedly
    * ``canceled``: Removed from the queue before it was started
  pid : int
    Job process of the processing service
  heartbeat : float
    Last sign of life of the job process (epoch seconds, so it's independent of time changes)
  run_at : datetime
    Scheduled run: the service doesn't take the job before this time. In UTC (docs/features/scheduled-stage-run.md).
    None: as soon as possible
  """



  def __init__(self, id: int|None=None, meta_file_id: int|None=None, stage_id: int|None=None, processing_step: str|None=None,
               continue_run: bool=True, user: str|None=None, status: Job_Status|str|None=None, error: str|None=None,
               create_time=None, start_time=None, end_time=None, pid: int|None=None, heartbeat: float|None=None, run_at=None):

    self.id: int|None = id
    self.meta_file_id: int|None = meta_file_id
    self.stage_id: int|None = stage_id
    self.processing_step: str|None = processing_step
    self.continue_run: bool = bool(continue_run)
    self.user: str|None = user
    self.status: Job_Status = Job_Status(status) if isinstance(status, str) else status or Job_Status.QUEUED
    self.error: str|None = error
    self.create_time: datetime.datetime = Processing_Job.get_datetime(create_time) or datetime.datetime.now()
    self.start_time: datetime.datetime|None = Processing_Job.get_datetime(start_time)
    self.end_time: datetime.datetime|None = Processing_Job.get_datetime(end_time)
    self.pid: int|None = pid
    self.heartbeat: float|None = heartbeat
    self.run_at: datetime.datetime|None = Processing_Job.get_datetime(run_at)



  @staticmethod
  def get_datetime(value) -> datetime.datetime|None:

    if isinstance(value, str):
      return datetime.datetime.fromisoformat(value)
    return value



  def is_active(self) -> bool:
    return self.status in [Job_Status.QUEUED, Job_Status.RUNNING]



  def is_scheduled(self) -> bool:
    return self.run_at is not None



  def is_waiting_for_its_time(self) -> bool:
    """Queued, and its time has not come yet"""
    return self.status == Job_Status.QUEUED and self.run_at is not None and self.run_at > utc_now()



  def get_dict(self) -> dict:
    return {
      'id': self.id,
      'meta_file_id': self.meta_file_id,
      'stage_id': self.stage_id,
      'processing_step': self.processing_step,
      'continue_run': self.continue_run,
      'user': self.user,
      'status': self.status.value,
      'error': self.error,
      'create_time': self.create_time.isoformat() if self.create_time else None,
      'start_time': self.start_time.isoformat() if self.start_time else None,
      'end_time': self.end_time.isoformat() if self.end_time else None,
      'pid': self.pid,
      'heartbeat': datetime.datetime.fromtimestamp(self.heartbeat).isoformat() if self.heartbeat else None,
      'run_at': format_utc(self.run_at) if self.run_at else None,
      }



#-----------------------------------------------------------------------------------------------
# Time of a scheduled run: always in UTC, so neither the time zone of the server
# nor the change to/from daylight saving time can move it
#-----------------------------------------------------------------------------------------------

def utc_now() -> datetime.datetime:
  return datetime.datetime.now(datetime.timezone.utc)



def format_utc(value: datetime.datetime) -> str:
  """
  The stored form, e.g. '2026-11-24T21:00:00+00:00'. Always the same length and offset,
  so the database can compare it as text.
  """
  return value.astimezone(datetime.timezone.utc).replace(microsecond=0).isoformat()



def format_utc_text(value: datetime.datetime) -> str:
  """For messages and the history, e.g. '2026-11-24 21:00 UTC'"""
  return value.astimezone(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')



def parse_run_at(value) -> datetime.datetime:
  """
  The time of a scheduled run, as sent by the web app or a client of the Web API.

  Args:
      value: ISO 8601 with time zone offset, e.g. '2026-11-24T22:00:00+01:00' or '2026-11-24T21:00:00Z'

  Raises:
      errors.Invalid_Input_Error: Not a time, without offset, or not in the future
  """

  if not isinstance(value, str) or value.strip() == '':
    raise errors.Invalid_Input_Error("'run_at' needs to be a date and time with time zone offset, e.g. '2026-11-24T22:00:00+01:00'")

  text = value.strip()
  # Python before 3.11 doesn't know 'Z'
  if text[-1:] in ('Z', 'z'):
    text = text[:-1] + '+00:00'

  try:
    run_at = datetime.datetime.fromisoformat(text)
  except ValueError:
    raise errors.Invalid_Input_Error(f"'run_at' is not a valid date and time: '{value}'. Example: '2026-11-24T22:00:00+01:00'") from None

  if run_at.tzinfo is None or run_at.utcoffset() is None:
    raise errors.Invalid_Input_Error(f"'run_at' needs a time zone offset, e.g. '2026-11-24T22:00:00+01:00' instead of '{value}'")

  run_at = run_at.astimezone(datetime.timezone.utc).replace(microsecond=0)

  if run_at <= utc_now():
    raise errors.Invalid_Input_Error(f"'run_at' is in the past: {format_utc_text(run_at)}")

  return run_at



# The job of the processing service which runs in this process (None: the run isn't a job)
current_job_id: contextvars.ContextVar[int|None] = contextvars.ContextVar('current_job_id', default=None)



def check_job_running() -> None:
  """
  Raises:
      Job_Ended_Exception: The job of this run isn't running anymore (e.g. it has been set to failed by the service)
  """

  job_id = current_job_id.get()
  if job_id is None:
    return

  from modules.db import processing_job_data
  job = processing_job_data.get_job(job_id)

  if job is None or job.status not in [Job_Status.QUEUED, Job_Status.RUNNING]:
    raise Job_Ended_Exception(f"The run has been ended: job {job_id} is '{job.status.value if job else 'removed'}'")



class Job_Ended_Exception(Exception):
  pass
