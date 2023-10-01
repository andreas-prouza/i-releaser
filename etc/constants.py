import os

C_LOCAL_BASE_DIR = f'{os.path.realpath(os.path.dirname(__file__)+"/..")}'

C_DEPLOY_VERSION = f'{C_LOCAL_BASE_DIR}/etc/deploy_version_{{project}}.json'
C_WORKFLOW = f'{C_LOCAL_BASE_DIR}/etc/workflow.json'
C_OBJECT_COMMANDS = f'{C_LOCAL_BASE_DIR}/etc/object_commands.json'
C_STAGE_COMMANDS = f'{C_LOCAL_BASE_DIR}/etc/stage_commands.json'

C_META_DIR = f"{C_LOCAL_BASE_DIR}/meta"
C_DEPLOY_DIR = f"{C_META_DIR}/{{create_date}}"
C_DEPLOY_META_FILE = f'{C_DEPLOY_DIR}/deployment_{{deploy_version}}.json'

#C_GNU_MAKE_OBJECT_LIST = 'objects.txt'
C_GNU_MAKE_OBJECT_LIST = 'tmp/prod_obj.txt'
C_COMPILED_OBJECT_LIST = 'tmp/compiled.txt'


# iconv will be used for convertion
C_CONVERT_OUTPUT = True
# https://docs.python.org/3/library/codecs.html#standard-encodings
C_CONVERT_FROM = 'cp1252'
C_CONVERT_TO = 'utf-8'


#---------------------------------------------------------
# GIT Settings
#---------------------------------------------------------
C_GIT_BRANCH_PRODUCTION = 'main'
C_GIT_BRANCH_RELEASE = '{project}-{deploy_version}'
#---------------------------------------------------------


C_PHYSICAL_FILE_ATTRIBUTES =  ['sqltable', 'pf']

# Definition of available steps within a stage
C_PRE = 'pre'
C_SAVE_INIT = 'save_init'
C_SAVE = 'save'
C_TRANSFER = 'transfer'
C_TARGET_PREPARE = 'target-prepare'
C_BACKUP_OLD_OBJ = 'backup-old-objects'
C_PERFORM_DEPLOYMENT = 'perform-deployment'
C_POST = 'post'

# Mapping for each step
# Define which python-file & function will be called for each step
# Command is in the format {filen-ame}.{function-name}
#   E.g.: file = pre.py; function = pre_cmd  
#         ==> cmd-string = 'pre.pre_cmd'
C_DEFAULT_STEP_2_CMD_MAPPING = [
  {
    "processing_step": C_PRE,
    "environment": "SCRIPT",
    "execute": 'pre.pre_cmd',
    "check_error": True
  },
  {
    "processing_step": C_SAVE_INIT,
    "environment": "SCRIPT",
    "execute": 'save_objects.set_init_cmds_for_save',
    "check_error": True
  },
  {
    "processing_step": C_SAVE,
    "environment": "SCRIPT",
    "execute": 'save_objects.set_cmd_object_to_savf',
    "check_error": True
  },
#  {
#    "processing_step": C_TRANSFER,
#    "environment": "SCRIPT",
#    "execute": 'transfer.set_cmd_transfer_to_target',
#    "check_error": True
#  },
#  {
#    "processing_step": C_TARGET_PREPARE,
#    "environment": "SCRIPT",
#    "execute": 'target_prepare.set_init_cmds_for_deployment',
#    "check_error": True
#  },
  {
    "processing_step": C_BACKUP_OLD_OBJ,
    "environment": "PASE",
    "execute": 'echo \'Not implemented\'',#  'backup.set_cmd_backup_objects_on_target',
    "check_error": True
  },
  {
    "processing_step": C_PERFORM_DEPLOYMENT,
    "environment": "SCRIPT",
    "execute": 'target_deployment.set_cmd_restore_objects_on_target',
    "check_error": True
  },
  {
    "processing_step": C_POST,
    "environment": "PASE",
    "execute": 'echo \'Not implemented\'',
    "check_error": True
  }
]