
from enum import Enum
from modules.stages import Stage
import datetime


class Action_type(Enum):

  RUN_STAGE = 'run_stage'
  SET_CHECK_ERROR = 'set_check_error'
  CHANGE_OBJ_READY_STATUS = 'change_obj_ready_status'
  CREATE_WF = 'create_workflow'
  CANCEL_WF = 'cancel_workflow'
  CUSTOM_ACTION = 'custom_action'
  

def create_action_log(action: Action_type, details: str|None=None, meta_file=None, stage: Stage|None=None) -> None:
  from modules import meta_file as mf

  user = mf.Meta_File.CURRENT_USER

  meta_file.processing_users.append({'action': action.value, 'user': user, 'timestamp' : str(datetime.datetime.now()), 'stage': stage.name if stage else None, 'details': details})