#---------------------------------------------------------
# Local settings of this installation. They override the defaults of etc/constants.py.
# This file is not tracked by git, so updates don't touch it.
#---------------------------------------------------------

# 'thread':  A stage runs in a thread of the web app
# 'service': A stage runs in a job of the processing service (see docs/processing-service.md)
#C_PROCESSING_MODE = 'service'

#C_SERVICE_MAX_PARALLEL_JOBS = 4

# Git branches
#C_GIT_BRANCH_PRODUCTION = 'main'
#C_GIT_BRANCH_RELEASE = '{project}-{deploy_version}'

# Timeout of PASE and QSYS commands in seconds. 0: no timeout
#C_COMMAND_TIMEOUT_SECONDS = 0

# Steps of a parallel group which run at the same time
#C_MAX_PARALLEL_STEPS = 4
