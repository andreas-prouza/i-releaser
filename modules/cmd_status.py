from __future__ import annotations
import logging
from enum import Enum



class Status(Enum):

  NEW = 'new'
  FINISHED = 'finished'
  IN_PROCESS = 'in process'
  IN_PREPERATION = 'in preperation'
  PREPARE = 'prepare'
  FAILED = 'failed'
  
