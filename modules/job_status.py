from enum import Enum



class Status(Enum):

  QUEUED = 'queued'
  RUNNING = 'running'
  FINISHED = 'finished'
  FAILED = 'failed'
  CANCELED = 'canceled'

