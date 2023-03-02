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