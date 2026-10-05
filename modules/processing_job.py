import datetime

from modules.job_status import Status as Job_Status




class Processing_Job:
  """
  Run of a stage which is processed by the processing service

  Parameters
  ----------
  user : str
    User who started the stage. The job is processed in the name of this user
  status : Job_Status
    * ``queued``: Waiting for the processing service
    * ``running``: A job process of the processing service runs the stage
    * ``finished``: The run of the stage has been finished successfully
    * ``failed``: The run of the stage failed or its job process ended unexpectedly
    * ``canceled``: Removed from the queue before it was started
  pid : int
    Job process of the processing service
  heartbeat : float
    Last sign of life of the job process (epoch seconds, so it's independent of time changes)
  """



  def __init__(self, id: int|None=None, meta_file_id: int|None=None, stage_id: int|None=None, processing_step: str|None=None,
               continue_run: bool=True, user: str|None=None, status: Job_Status|str|None=None, error: str|None=None,
               create_time=None, start_time=None, end_time=None, pid: int|None=None, heartbeat: float|None=None):

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



  @staticmethod
  def get_datetime(value) -> datetime.datetime|None:

    if isinstance(value, str):
      return datetime.datetime.fromisoformat(value)
    return value



  def is_active(self) -> bool:
    return self.status in [Job_Status.QUEUED, Job_Status.RUNNING]



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
      'heartbeat': datetime.datetime.fromtimestamp(self.heartbeat).isoformat() if self.heartbeat else None
      }
