import os

C_LOCAL_BASE_DIR = f'{os.path.realpath(os.path.dirname(__file__)+"/..")}'

C_DEPLOY_VERSION = f'{C_LOCAL_BASE_DIR}/etc/deploy_version_{{project}}.json'
C_WORKFLOW = f'{C_LOCAL_BASE_DIR}/etc/workflow.json'
C_OBJECT_COMMANDS = f'{C_LOCAL_BASE_DIR}/etc/object_commands.json'
C_STAGE_COMMANDS = f'{C_LOCAL_BASE_DIR}/etc/stage_commands.json'

C_META_DIR = f"{C_LOCAL_BASE_DIR}/meta"
C_DEPLOY_DIR = f"{C_META_DIR}/{{create_date}}/{{deploy_version}}"
C_DEPLOY_META_FILE = f'{C_DEPLOY_DIR}/deployment_{{deploy_version}}.json'

#C_OBJECT_LIST = 'objects.txt'
C_OBJECT_LIST = 'build-output/object-list.txt'

# The old build script, wrote each object into the following file, when compile has been finished
#   E.g.: echo "build/prouzalib/testsqlerr.sqlrpgle.pgm.obj|"`date` >> ./tmp/compiled.txt
C_COMPILED_OBJECT_LIST = 'build-output/compiled.txt'


# iconv will be used for convertion
C_CONVERT_OUTPUT = False
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


# Mapping for each step
# Define which python-file & function will be called for each step
# Command is in the format {filen-ame}.{function-name}
#   E.g.: file = pre.py; function = pre_cmd  
#         ==> cmd-string = 'pre.pre_cmd'
C_DEFAULT_STEP_2_CMD_MAPPING = [
  {
    "processing_step": 'pre',
    "environment": "SCRIPT",
    "execute": 'pre.pre_cmd',
    "check_error": True
  },
  {
    "processing_step": 'save-prepare',
    "environment": "SCRIPT",
    "execute": 'save_objects.init_save',
    "check_error": True
  },
  {
    "processing_step": 'save',
    "environment": "SCRIPT",
    "execute": 'save_objects.save_objects_to_savf',
    "check_error": True
  },
  {
    "processing_step": 'transfer',
    "environment": "SCRIPT",
    "execute": 'transfer.transfer_to_target',
    "check_error": True
  },
  {
    "processing_step": 'target-prepare',
    "environment": "SCRIPT",
    "execute": 'target_prepare.init_deployment',
    "check_error": True
  },
  {
    "processing_step": 'backup-old-objects',
    "environment": "SCRIPT",
    "execute": 'backup_old_objects.backup_objects_on_target',
    "check_error": True
  },
  {
    "processing_step": 'perform-deployment',
    "environment": "SCRIPT",
    "execute": 'target_deployment.restore_objects_on_target',
    "check_error": True
  },
  {
    "processing_step": 'post',
    "environment": "PASE",
    "execute": 'echo \'Not implemented\'',
    "check_error": True
  }
]