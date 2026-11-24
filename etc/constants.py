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

# Notifications by e-mail and webhooks (docs/features/notifications.md). Without the file there are none.
C_NOTIFICATIONS_CONFIG = f'{C_LOCAL_BASE_DIR}/etc/notifications.json'

# Backups of the database (var/backup) which are kept. A backup is made before the database gets updated.
C_DB_BACKUP_COUNT = 5

# Maximum size of the custom data of a deployment (bytes of its JSON)
C_MAX_CUSTOM_DATA_SIZE = 64 * 1024

# Maximum size of the compile list of a deployment (bytes of its JSON), see docs/webapi.md#create-a-deployment
C_MAX_COMPILE_LIST_SIZE = 32 * 1024 * 1024

# Default timeout of PASE and QSYS commands in seconds. 0: no timeout
C_COMMAND_TIMEOUT_SECONDS = 0

# Steps of a parallel group which run at the same time. Further steps of the group wait for a free slot.
C_MAX_PARALLEL_STEPS = 4

# Failed logins until further logins are blocked (docs/bugfixes/login-can-disable-ibm-i-profiles.md):
# * of a user: failed IBM i sign-ons in a row. Blocked until an admin unblocks it (settings page) or the user had a successful login before.
#   Keep it below the system value QMAXSIGN (IBM default 3), so the IBM i profiles don't get disabled.
# * from a client address: C_LOGIN_CLIENT_MAX_FAILURES failed logins within C_LOGIN_BLOCK_MINUTES. Ends by itself.
C_LOGIN_MAX_FAILURES = 2
C_LOGIN_CLIENT_MAX_FAILURES = 10
C_LOGIN_BLOCK_MINUTES = 15
# The sign-on on the IBM i fails if it takes longer (seconds)
C_LOGIN_TIMEOUT_SECONDS = 15
# Logins which wait for the IBM i at the same time, per process of the web app. More get 503.
C_LOGIN_MAX_PARALLEL = 4

# Address of the web app for the users, e.g. 'https://ireleaser.example.com' (scheme and host). Requests with this origin are
# accepted behind a reverse proxy which doesn't keep the Host header, and links (e.g. in notifications) use it. Empty: the Host header.
C_EXTERNAL_URL = ''

# Days until an API token expires (docs/bugfixes/api-token-outlives-user.md). 0: never.
# Tokens of older versions expire this many days after their first use with this version.
C_TOKEN_MAX_DAYS = 365

# Data retention (docs/features/data-retention.md): deployments which are finished or canceled and haven't changed for this many days
# are removed with their directory in meta/, once a day (0: keep everything). The newest finished deployment of a project stays.
C_RETENTION_DAYS = 0
# Archive them before (var/archive/{project}/{version}-{id}.tar.gz)
C_RETENTION_ARCHIVE = False
# Deployments removed by one run at most
C_RETENTION_MAX_PER_RUN = 100
# Log files are rotated at the start of the web app and the processing service if they are larger (MB); this many old ones are kept
C_LOG_MAX_MB = 50
C_LOG_BACKUPS = 5

# Audit log of security events (docs/features/audit-log.md): days they are kept (0: always),
# and an optional file which gets each event as a JSON line (e.g. for a SIEM)
C_AUDIT_RETENTION_DAYS = 730
C_AUDIT_FILE = ''

# The health check (/healthz) reports an error if less space is free in var/ or meta/ (MB)
C_HEALTH_MIN_FREE_MB = 500

# The live updates of a page check every this many seconds whether the session and the permission are still valid
C_WATCH_SESSION_CHECK_SECONDS = 60

# Two-factor authentication with an authenticator app (docs/features/two-factor-authentication.md):
# 'off', 'optional' (each user decides), 'admins' (required for users with the permission admin), 'required' (all users)
C_2FA_POLICY = 'optional'
# Some actions (create an API token, change permissions or settings) need a code entered within this time
C_2FA_STEP_UP_MINUTES = 10
# Wrong codes of a user within C_LOGIN_BLOCK_MINUTES, until no more codes are accepted
C_2FA_MAX_FAILURES = 5

#---------------------------------------------------------
# Processing of stages
#---------------------------------------------------------
# 'thread':  A stage runs in a thread of the web app
# 'service': A stage runs in a job of the processing service (see docs/processing-service.md)
C_PROCESSING_MODE = 'thread'

# Settings changed in the web app (Settings -> General) are stored here: the processing mode
# (overrides C_PROCESSING_MODE) and the auto start of the processing service
C_APP_SETTINGS_FILE = f'{C_LOCAL_BASE_DIR}/etc/app.json'

C_SERVICE_SOCKET = f'{C_LOCAL_BASE_DIR}/var/processing-service.sock'
# The PID file and the stopped file need to match serviceapp/service
C_SERVICE_PID_FILE = f'{C_LOCAL_BASE_DIR}/var/processing-service.pid'
# Exists after `serviceapp/service stop`: the auto start is paused until the next start
C_SERVICE_STOPPED_FILE = f'{C_LOCAL_BASE_DIR}/var/processing-service.stopped'
# Held by the running service, so only one service runs at the same time
C_SERVICE_LOCK_FILE = f'{C_LOCAL_BASE_DIR}/var/processing-service.lock'

# Seconds between two checks of the web app whether the processing service is running (auto start)
C_SERVICE_WATCHDOG_INTERVAL = 60

# Seconds between two checks of the queue, if the service has not been woken up by the web app
C_SERVICE_POLL_INTERVAL = 5
C_SERVICE_MAX_PARALLEL_JOBS = 4

# A running job gives a sign of life every C_SERVICE_HEARTBEAT_INTERVAL seconds.
# Without one for C_SERVICE_HEARTBEAT_TIMEOUT seconds, its run is set to failed.
C_SERVICE_HEARTBEAT_INTERVAL = 10
C_SERVICE_HEARTBEAT_TIMEOUT = 60

# A scheduled run of a stage which the service takes more than this after its time is not run
# (e.g. the service wasn't running), so a night deployment doesn't start during the day. 0: no limit
C_SCHEDULE_MAX_DELAY_MINUTES = 60
#---------------------------------------------------------

#---------------------------------------------------------
# GIT Settings
#---------------------------------------------------------
C_GIT_BRANCH_PRODUCTION = 'main'
C_GIT_BRANCH_RELEASE = '{project}-{deploy_version}'
#---------------------------------------------------------


C_PHYSICAL_FILE_ATTRIBUTES =  ['sqltable', 'pf']


#---------------------------------------------------------
# Web app
#---------------------------------------------------------
# True: the Content-Security-Policy is only reported in the console of the browser, not enforced
# (Content-Security-Policy-Report-Only). For the time an installation moves its custom templates to script files
# (docs/features/web-ui-security-headers.md). The web app logs a warning at its start.
C_CSP_REPORT_ONLY = False
#---------------------------------------------------------


#---------------------------------------------------------
# Local settings
#---------------------------------------------------------
try:
    from etc.settings import *
except ModuleNotFoundError as e:
    if e.name != 'etc.settings':
        raise
