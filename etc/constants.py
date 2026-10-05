import os


C_APP_VERSION = '2.0.2'

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

C_JIRA_CONFIG = f'{C_LOCAL_BASE_DIR}/etc/jira.json'

#---------------------------------------------------------
# Processing of stages
#---------------------------------------------------------
# 'thread':  A stage runs in a thread of the web app
# 'service': A stage runs in a job of the processing service (see docs/processing-service.md)
C_PROCESSING_MODE = 'thread'

C_SERVICE_SOCKET = f'{C_LOCAL_BASE_DIR}/var/processing-service.sock'
C_SERVICE_PID_FILE = f'{C_LOCAL_BASE_DIR}/var/processing-service.pid'

# Seconds between two checks of the queue, if the service has not been woken up by the web app
C_SERVICE_POLL_INTERVAL = 5
C_SERVICE_MAX_PARALLEL_JOBS = 4

# A running job gives a sign of life every C_SERVICE_HEARTBEAT_INTERVAL seconds.
# Without one for C_SERVICE_HEARTBEAT_TIMEOUT seconds, its run is set to failed.
C_SERVICE_HEARTBEAT_INTERVAL = 10
C_SERVICE_HEARTBEAT_TIMEOUT = 60
#---------------------------------------------------------

#---------------------------------------------------------
# GIT Settings
#---------------------------------------------------------
C_GIT_BRANCH_PRODUCTION = 'main'
C_GIT_BRANCH_RELEASE = '{project}-{deploy_version}'
#---------------------------------------------------------


C_PHYSICAL_FILE_ATTRIBUTES =  ['sqltable', 'pf']

