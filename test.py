import logging, sys, os
#from io import StringIO

from etc import logger_config, constants
from modules import deploy_action, workflow, meta_file, deploy_version
from modules.cmd_status import Status
import datetime


print(os.path.join('test', 'xxx', '/'))
print(datetime.datetime.now().strftime('%F %T.%f')[:-3])

i=0
while i< 1.2:
  print(3 + i)
  i+=0.1

exit



class Test:
    id = 0

    def __init__(self, id=None):
      self.id = id
      if self.id is None:
        Test.id =+ 1
        self.id = Test.id

    def printVal(self, id=None):
      print(f"{Test.id=} {id=}")


print(type(True))

a='3'

if int(a) == 3:
  print('OK')

t0 = Test(2)
t0.printVal(111)
t1 = Test()
t1.printVal(222)
t2 = Test(3)
t3 = Test()
t2.printVal(333)
t3.printVal()


exit


step_action = [
      {
        "processing_step": "pre",
        "environment": "SCRIPT",
        "execute": "pre.pre_cmd",
        "check_error": True
      },
      {
        "processing_step": "print_pwd",
        "environment": "PASE",
        "execute": "pwd",
        "check_error": True
      },
      {
        "processing_step": "create_compile_script",
        "environment": "SCRIPT",
        "execute": "build.create_compile_script",
        "check_error": True
      },
      {
        "processing_step": "clean_current_commit",
        "environment": "SCRIPT",
        "execute": "build.clean_current_commit",
        "check_error": True
      },
      {
        "processing_step": "git_save_changes",
        "environment": "SCRIPT",
        "execute": "build.git_save_changes",
        "check_error": True
      },
      {
        "processing_step": "run_build",
        "environment": "PASE",
        "execute": "scripts/cleanup.sh  && scripts/run_build.sh",
        "check_error": True
      },
      {
        "processing_step": "create_object_list",
        "environment": "PASE",
        "execute": "scripts/cleanup.sh  && scripts/create_build_script.sh",
        "check_error": True
      },
      {
        "processing_step": "merge_results",
        "environment": "SCRIPT",
        "execute": "build.merge_results",
        "check_error": True
      },
      {
        "processing_step": "load_object_list",
        "environment": "SCRIPT",
        "execute": "build.load_object_list",
        "check_error": True
      }
    ]

#constants.C_DEFAULT_STEP_2_CMD_MAPPING

#merged_list = [(d1 | d2) for d1, d2 in zip(constants.C_DEFAULT_STEP_2_CMD_MAPPING, wf["step_action"])]
#logging.debug(f"{merged_list=}")