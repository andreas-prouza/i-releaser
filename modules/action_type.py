
from enum import Enum

class Action_type(Enum):

  RUN_STAGE = 'run_stage'
  SET_CHECK_ERROR = 'set_check_error'
  RESET_STAGE_STATUS = 'reset_stage_status'
  RESET_DEPLOYMENT_STATUS = 'reset_deployment_status'
  CHANGE_OBJ_READY_STATUS = 'change_obj_ready_status'
  CREATE_WF = 'create_workflow'
  CANCEL_WF = 'cancel_workflow'
  CUSTOM_ACTION = 'custom_action'
  
