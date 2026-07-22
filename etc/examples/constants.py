import os


C_APP_VERSION = '2.0.0'

C_LOCAL_BASE_DIR = f'{os.path.realpath(os.path.dirname(__file__)+"/..")}'

C_APP_DB_FILE = f'{C_LOCAL_BASE_DIR}/var/app.sqlite'

C_WORKFLOW = f'{C_LOCAL_BASE_DIR}/etc/workflow.json'
C_WORKFLOWS_DIR = f'{C_LOCAL_BASE_DIR}/etc/workflows'
C_OBJECT_COMMANDS = f'{C_LOCAL_BASE_DIR}/etc/object_commands.json'
C_STAGE_COMMANDS = f'{C_LOCAL_BASE_DIR}/etc/stage_commands.json'
C_DEFAULT_STEP_ACTION = f'{C_LOCAL_BASE_DIR}/etc/default_step_action.json'

C_META_DIR = f"{C_LOCAL_BASE_DIR}/meta/{{project}}/{{create_date}}/{{deploy_version}}"

C_OBJECT_LIST = './build-output/object-list.txt'

C_USER_PERMISSIONS = f'{C_LOCAL_BASE_DIR}/etc/user_permissions.json'

#---------------------------------------------------------
# GIT Settings
#---------------------------------------------------------
C_GIT_BRANCH_PRODUCTION = 'main'
C_GIT_BRANCH_RELEASE = '{project}-{deploy_version}'
#---------------------------------------------------------


C_PHYSICAL_FILE_ATTRIBUTES =  ['sqltable', 'pf']

