
from enum import Enum
from modules import meta_file as mf
from modules.stages import Stage
import datetime


class Action_type(Enum):

  RUN_STAGE = 'run_stage'
  SET_CHECK_ERROR = 'set_check_error'
  CHANGE_OBJ_READY_STATUS = 'change_obj_ready_status'
  CREATE_WF = 'create_workflow'
  CANCEL_WF = 'cancel_workflow'
  

def create_action_log(action: Action_type, details: str=None, meta_file: mf.Meta_File=None, stage: Stage=None) -> None:

  user = mf.Meta_File.CURRENT_USER

  if stage is not None:
    stage.processing_users.append({'action': action.value, 'user': user, 'timestamp' : str(datetime.datetime.now()), 'details': details})
    details = f"Stage {stage.name}: {details}" if details is not None else f"Stage {stage.name}"
  
  meta_file.processing_users.append({'action': action.value, 'user': user, 'timestamp' : str(datetime.datetime.now()), 'details': details})