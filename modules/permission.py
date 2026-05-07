from enum import Enum
from typing import List, Dict, Optional
from pydantic import BaseModel



class PermissionAction(Enum):

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




class PermissionWorkflowStages(BaseModel):
  stages: Dict[str, List[str]]

class PermissionWorkflow(BaseModel):
  general: Optional[List[str]]
  stages: Optional[Dict[str, List[str]]]

class Permissions(BaseModel):
  roles: Optional[List[str]]
  general: Optional[List[str]]
  workflows: Optional[Dict[str, PermissionWorkflow]]