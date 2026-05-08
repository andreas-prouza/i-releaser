from enum import Enum
from typing import Any, List, Dict, Optional
from dataclasses import dataclass, field



class PermissionAction(Enum):

  ADMIN = 'admin'
  READ = 'read'
  START_WORKFLOW = 'start workflow'
  UPDATE = 'update'
  DEPLOY = 'deploy'
  RUN_WORKFLOW = 'run'
  CHANGE_CHECK_ERROR = 'change check error'
  FOUR_EYES_CHECK = '4-eyes check'
  CANCEL_WORKFLOW = 'cancel workflow'

  
PERMISSION_DEPENDENCIES = {
  PermissionAction.ADMIN: [
    PermissionAction.CANCEL_WORKFLOW, 
    PermissionAction.START_WORKFLOW, 
    PermissionAction.UPDATE, 
    PermissionAction.READ, 
    PermissionAction.DEPLOY, 
    PermissionAction.FOUR_EYES_CHECK, 
    PermissionAction.CHANGE_CHECK_ERROR, 
    PermissionAction.RUN_WORKFLOW
    ],
  PermissionAction.DEPLOY: [
    PermissionAction.READ
    ],
  PermissionAction.FOUR_EYES_CHECK: [
    PermissionAction.READ, 
    PermissionAction.DEPLOY
    ],
  PermissionAction.RUN_WORKFLOW: [
    PermissionAction.START_WORKFLOW, 
    PermissionAction.UPDATE
    ],
  PermissionAction.UPDATE: [
    PermissionAction.READ
    ],
  PermissionAction.START_WORKFLOW: [
    PermissionAction.UPDATE
    ],
  PermissionAction.CHANGE_CHECK_ERROR: [
    PermissionAction.UPDATE
    ],
  PermissionAction.CANCEL_WORKFLOW: [
    PermissionAction.UPDATE
    ]
}




@dataclass
class PermissionWorkflowStages:
  stages: Dict[str, List[PermissionAction]]


@dataclass
class PermissionWorkflow:
  general: List[PermissionAction] = field(default_factory=list)
  stages: Dict[str, List[PermissionAction]] = field(default_factory=dict)


@dataclass
class Permissions:
  roles: List[str] = field(default_factory=list)
  general: List[PermissionAction] = field(default_factory=list)
  workflows: Dict[str, PermissionWorkflow] = field(default_factory=dict)

  def __post_init__(self):
    # Check if the items in general are strings, and convert them if so
    if self.general:
      self.general = [
        PermissionAction(action) if isinstance(action, str) else action for action in self.general
      ]