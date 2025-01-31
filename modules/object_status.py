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
    IN_BACKUP = 'in backup'
    BACKUPED = 'backuped'
    IN_RESTORE = 'restoring'
    RESTORED = 'restored'
    FAILED = 'failed'
    IN_BUILD = 'in build'
    BUILDED = 'builded'


STATUS_RANKING = [
  Status.NEW,
  Status.IN_BUILD,
  Status.BUILDED,
  Status.IN_SAVE,
  Status.SAVED,
  Status.IN_TRANSVER,
  Status.TRANSVERRED,
  Status.IN_RESTORE,
  Status.RESTORED,
  Status.FINISHED
]
