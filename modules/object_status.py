from __future__ import annotations
import logging
from enum import Enum



class Status(Enum):

  NEW = 'new'
  FINISHED = 'finished'
  IN_PROCESS = 'in process'
  IN_PREPERATION = 'in preperation'
  IN_SAVE = 'saving'
  SAVED = 'saved'
  IN_TRANSVER = 'in transfer'
  TRANSVERRED = 'transferred'
  IN_RESTORE = 'restoring'
  RESTORED = 'restored'
  FAILED = 'failed'
  
