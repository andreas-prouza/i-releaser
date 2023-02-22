
import datetime
import json
import logging

from etc import logger_config, constants
from modules import meta_file, ibm_i_commands, deploy_action as da


meta_file = meta_file.Meta_File()
meta_file.import_objects_from_config_file(constants.C_GNU_MAKE_OBJECT_LIST)
meta_file.deploy_objects.load_actions_from_json(constants.C_OBJECT_COMMANDS)

commands = ibm_i_commands.IBM_i_commands(meta_file)
commands.set_init_cmds()
commands.set_save_objects_cmd()
commands.set_prepear_cmd_for_target()

commands.run_commands(da.Processing_Area.SAVE)