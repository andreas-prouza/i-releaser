from __future__ import annotations
import logging
from enum import Enum



class Permission(Enum):

    ADMIN = 'admin'
    READ = 'read'
    DEPLOY = 'deploy'
    CHANGE_CHECK_ERROR = 'change_check_error'
    FOUR_EYES_CHECK = '4-eyes_check'
