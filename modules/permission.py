from __future__ import annotations
import logging
from enum import Enum


class Permission(Enum):

  ADMIN = 'admin'
  READ = 'read'
  START_WORKFLOW = 'start_workflow'
  UPDATE = 'update'
  DEPLOY = 'deploy'
  RUN_WORKFLOW = 'run'
  CHANGE_CHECK_ERROR = 'change_check_error'
  FOUR_EYES_CHECK = '4-eyes_check'
  CANCEL_WORKFLOW = 'cancel_workflow'

  
PERMISSION_DEPENDENCIES = {
  Permission.ADMIN: [
    Permission.CANCEL_WORKFLOW, 
    Permission.START_WORKFLOW, 
    Permission.UPDATE, 
    Permission.READ, 
    Permission.DEPLOY, 
    Permission.FOUR_EYES_CHECK, 
    Permission.CHANGE_CHECK_ERROR, 
    Permission.RUN_WORKFLOW
    ],
  Permission.DEPLOY: [
    Permission.READ
    ],
  Permission.FOUR_EYES_CHECK: [
    Permission.READ, 
    Permission.DEPLOY
    ],
  Permission.RUN_WORKFLOW: [
    Permission.START_WORKFLOW, 
    Permission.UPDATE
    ],
  Permission.UPDATE: [
    Permission.READ
    ],
  Permission.START_WORKFLOW: [
    Permission.UPDATE
    ],
  Permission.CHANGE_CHECK_ERROR: [
    Permission.UPDATE
    ],
  Permission.CANCEL_WORKFLOW: [
    Permission.UPDATE
    ]
}
