
import datetime
import json
import logging

from etc import logger_config, constants
from modules import meta_file, ibm_i_commands, deploy_action as da


meta_file = meta_file.Meta_File(workflow_name='default')
meta_file.import_objects_from_config_file(constants.C_GNU_MAKE_OBJECT_LIST)
meta_file.load_actions_from_json(constants.C_OBJECT_COMMANDS)
meta_file.write_meta_file()

exit(0)

commands = ibm_i_commands.IBM_i_commands(meta_file)

for stage in meta_file.current_stages:
  print(f"Run all commands for stage {stage.name}")
  commands.set_cmds(stage=stage.name)
  commands.run_commands(stage=stage.name)

meta_file.set_next_stage(from_stage='START')
commands.set_cmds(stage='UAT')
commands.run_commands(stage='UAT')

#for stage in meta_file.current_stages:
#  print(f"Run all commands for stage {stage.name}")
#  commands.set_cmds(stage=stage.name)
#  commands.run_commands(stage=stage.name)

