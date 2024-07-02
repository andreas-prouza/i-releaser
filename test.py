import logging, sys
from io import StringIO

from etc import logger_config, constants
#from modules import deploy_action, workflow
#from modules.cmd_status import Status

#actions = deploy_action.Deploy_Action_List_list()
#actions.add_action(deploy_action.Deploy_Action('test', 0, Status.NEW, deploy_action.Command_Type.PASE, 'STARTX', 'pre'))

#print(actions.get_actions_as_dict())

step_2_script_mapping = [
      {
        "processing_step": "pre",
        "environment": "SCRIPT",
        "execute": "pre.pre_cmd",
        "check_error": True
      },
      {
        "processing_step": "print_pwd",
        "environment": "PASE",
        "execute": "pwd",
        "check_error": True
      },
      {
        "processing_step": "prepare_build",
        "environment": "SCRIPT",
        "execute": "build.prepare_build",
        "check_error": True
      },
      {
        "processing_step": "clean_current_commit",
        "environment": "SCRIPT",
        "execute": "build.clean_current_commit",
        "check_error": True
      },
      {
        "processing_step": "git_save_changes",
        "environment": "SCRIPT",
        "execute": "build.git_save_changes",
        "check_error": True
      },
      {
        "processing_step": "run_build",
        "environment": "PASE",
        "execute": "scripts/cleanup.sh  && scripts/run_build.sh",
        "check_error": True
      },
      {
        "processing_step": "create_object_list",
        "environment": "PASE",
        "execute": "scripts/cleanup.sh  && scripts/create_build_script.sh",
        "check_error": True
      },
      {
        "processing_step": "merge_results",
        "environment": "SCRIPT",
        "execute": "build.merge_results",
        "check_error": True
      },
      {
        "processing_step": "load_object_list",
        "environment": "SCRIPT",
        "execute": "build.load_object_list",
        "check_error": True
      }
    ]

constants.C_DEFAULT_STEP_2_CMD_MAPPING

merged_list = [(d1 | d2) for d1, d2 in zip(constants.C_DEFAULT_STEP_2_CMD_MAPPING, wf["step_2_script_mapping"])]
logging.debug(f"{merged_list=}")