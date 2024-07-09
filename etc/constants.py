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

# Mapping for each step
# Definition for Python scripts have a simple format to follow:
#   Command is in the format {file-name}.{function-name}
#   E.g.: file = pre.py; function = pre_cmd  
#         ==> cmd-string = 'pre.pre_cmd'
C_DEFAULT_STEP_ACTION = 'etc/default_step_action.json'

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

