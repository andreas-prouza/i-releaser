from enum import Enum

class Meta_file_status(Enum):
  NEW = 'new'
  READY = 'ready'
  IN_PROCESS = 'in process'
  FAILED = 'failed'
  FINISHED = 'finished'
  CANCELED = 'canceled'
