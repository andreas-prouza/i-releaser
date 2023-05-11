C_LOCAL_BASE_DIR = '/home/andreas/projekte/deployment'

C_DEPLOY_VERSION = 'etc/deploy_version.json'
C_STAGES = 'etc/stages.json'
C_OBJECT_COMMANDS = 'etc/object_commands.json'
C_STAGE_COMMANDS = 'etc/stage_commands.json'

C_META_DIR = f"{C_LOCAL_BASE_DIR}/meta"
C_DEPLOY_DIR = f"{C_META_DIR}/{{deploy_version}}-{{create_date}}"
C_DEPLOY_META_FILE = f'{C_DEPLOY_DIR}/deployment_{{deploy_version}}.json'

#C_GNU_MAKE_OBJECT_LIST = 'objects.txt'
C_GNU_MAKE_OBJECT_LIST = 'prod_obj.txt'


# iconv will be used for convertion
C_CONVERT_OUTPUT = True
# https://docs.python.org/3/library/codecs.html#standard-encodings
C_CONVERT_FROM = 'cp1252'
C_CONVERT_TO = 'utf-8'

C_PHYSICAL_FILE_ATTRIBUTES =  ['sqltable', 'pf']

# Definition of available steps within a stage
C_PRE = 'pre'
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
C_STEP_2_CMD_MAPPING = {
  C_PRE:
    [
      'pre.pre_cmd'
    ],
  C_POST:
    [
    ],
  C_SAVE: 
    [
      'save_objects.set_init_cmds_for_save', 
      'save_objects.set_cmd_object_to_savf'
    ],
  C_TRANSFER:
    [
      'transfer.set_cmd_transfer_to_target'
    ],
  C_TARGET_PREPARE:
    [
      'target_prepare.set_init_cmds_for_deployment'
    ],
  C_BACKUP_OLD_OBJ:
    [
    #  'backup.set_cmd_backup_objects_on_target'
    ],
  C_PERFORM_DEPLOYMENT:
    [
      'target_deployment.set_cmd_restore_objects_on_target'
    ]
  }