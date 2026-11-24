#---------------------------------------------------------
# Local settings of this installation. They override the defaults of etc/constants.py.
# This file is not tracked by git, so updates don't touch it.
#---------------------------------------------------------

# 'thread':  A stage runs in a thread of the web app
# 'service': A stage runs in a job of the processing service (see docs/processing-service.md)
#C_PROCESSING_MODE = 'service'

#C_SERVICE_MAX_PARALLEL_JOBS = 4

# A scheduled run of a stage which starts more than this many minutes late is not run
#C_SCHEDULE_MAX_DELAY_MINUTES = 60

# Git branches
#C_GIT_BRANCH_PRODUCTION = 'main'
#C_GIT_BRANCH_RELEASE = '{project}-{deploy_version}'

# Timeout of PASE and QSYS commands in seconds. 0: no timeout
#C_COMMAND_TIMEOUT_SECONDS = 0

# Steps of a parallel group which run at the same time
#C_MAX_PARALLEL_STEPS = 4

# Two-factor authentication with an authenticator app (docs/features/two-factor-authentication.md):
# 'off', 'optional' (each user decides, the default), 'admins' (required for admins), 'required' (all users).
# Recommended: 'admins'. Each admin then sets it up at the next login: keep the recovery codes.
#C_2FA_POLICY = 'admins'

# Failed logins: a user is blocked after this many wrong passwords in a row, until an admin unblocks it.
# Keep it below the system value QMAXSIGN of the IBM i (IBM default 3).
#C_LOGIN_MAX_FAILURES = 2
