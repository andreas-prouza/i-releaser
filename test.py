import logging, sys
from io import StringIO

from etc import logger_config, constants
from modules import deploy_action
from modules.cmd_status import Status

actions = deploy_action.Deploy_Action_List_list()
actions.add_action(deploy_action.Deploy_Action('test', 0, Status.NEW, deploy_action.Command_Type.PASE, 'STARTX', 'pre'))

print(actions.get_actions_as_dict())

