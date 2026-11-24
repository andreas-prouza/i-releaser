
from enum import Enum

class Action_type(Enum):

  RUN_STAGE = 'run_stage'
  SCHEDULE_STAGE = 'schedule_stage'
  CANCEL_SCHEDULE = 'cancel_schedule'
  SCHEDULED_RUN_FAILED = 'scheduled_run_failed'
  SET_CHECK_ERROR = 'set_check_error'
  RESET_STAGE_STATUS = 'reset_stage_status'
  RESET_DEPLOYMENT_STATUS = 'reset_deployment_status'
  RESET_LAST_FINISHED_STAGE = 'reset_last_finished_stage'
  CHANGE_OBJ_READY_STATUS = 'change_obj_ready_status'
  CREATE_WF = 'create_workflow'
  CANCEL_WF = 'cancel_workflow'
  CUSTOM_ACTION = 'custom_action'
  EDIT_CUSTOM_DATA = 'edit_custom_data'
  APPROVE_STAGE = 'approve_stage'
  APPROVAL_INVALID = 'approval_invalid'
  
