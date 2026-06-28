from enum import Enum



class Status(Enum):

  NEW = 'new'
  READY = 'ready'
  FINISHED = 'finished'
  IN_PROCESS = 'in process'
  IN_PREPERATION = 'in preperation'
  PREPARE = 'prepare'
  FAILED = 'failed'
  
