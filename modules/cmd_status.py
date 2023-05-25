from __future__ import annotations
import logging
from enum import Enum



class Status(Enum):

  NEW = 'new'
  FINISHED = 'finished'
  IN_PROCESS = 'in process'
  FAILED = 'failed'
  
