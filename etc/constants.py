import os

#---------------------------------------------------------
# Defaults. Don't change them here: put your own values into etc/settings.py,
# it's loaded at the end of this file and not tracked by git.
#---------------------------------------------------------

C_LOCAL_BASE_DIR = f'{os.path.realpath(os.path.dirname(__file__)+"/..")}'

C_APP_DB_FILE = f'{C_LOCAL_BASE_DIR}/var/app.sqlite'

C_WORKFLOW = f'{C_LOCAL_BASE_DIR}/etc/workflow.json'
C_WORKFLOWS_DIR = f'{C_LOCAL_BASE_DIR}/etc/workflows'
C_OBJECT_COMMANDS = f'{C_LOCAL_BASE_DIR}/etc/object_commands.json'
C_DEFAULT_STEP_ACTION = f'{C_LOCAL_BASE_DIR}/etc/default_step_action.json'

C_META_DIR = f"{C_LOCAL_BASE_DIR}/meta/{{project}}/{{create_date}}/{{deploy_version}}"

C_OBJECT_LIST = './build-output/object-list.txt'

# Directories for object lists given to the Web API, in addition to the build_dir of the workflow's stages
C_OBJECT_LIST_DIRS = []

C_USER_PERMISSIONS = f'{C_LOCAL_BASE_DIR}/etc/user_permissions.json'

C_JIRA_CONFIG = f'{C_LOCAL_BASE_DIR}/etc/jira.json'

C_DB_DEPLOYMENT_CONFIG = f'{C_LOCAL_BASE_DIR}/etc/db_deployment.json'

# Backups of the database (var/backup) which are kept. A backup is made before the database gets updated.
C_DB_BACKUP_COUNT = 5

# Maximum size of the custom data of a deployment (bytes of its JSON)
C_MAX_CUSTOM_DATA_SIZE = 64 * 1024

# Default timeout of PASE and QSYS commands in seconds. 0: no timeout
C_COMMAND_TIMEOUT_SECONDS = 0

# Steps of a parallel group which run at the same time. Further steps of the group wait for a free slot.
C_MAX_PARALLEL_STEPS = 4

# Failed logins per user and per client address, until further logins are blocked.
# Keep it below the system value QMAXSIGN, so the IBM i profiles don't get disabled.
C_LOGIN_MAX_FAILURES = 5
C_LOGIN_BLOCK_MINUTES = 15

#---------------------------------------------------------
# Processing of stages
#---------------------------------------------------------
# 'thread':  A stage runs in a thread of the web app
# 'service': A stage runs in a job of the processing service (see docs/processing-service.md)
C_PROCESSING_MODE = 'thread'

# The mode changed in the web app (Settings -> General) is stored here and overrides C_PROCESSING_MODE
C_WEB_SETTINGS_FILE = f'{C_LOCAL_BASE_DIR}/etc/web_settings.json'

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


#---------------------------------------------------------
# Local settings
#---------------------------------------------------------
try:
  from etc.settings import *
except ModuleNotFoundError as e:
  if e.name != 'etc.settings':
    raise
