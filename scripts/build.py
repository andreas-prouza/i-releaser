from __future__ import annotations
import os, logging, sys
import subprocess
import datetime
from pathlib import Path

sys.path.insert(0, os.path.realpath(os.path.dirname(__file__) + '/..'))

#################################################################

from etc import logger_config

from etc import constants
from modules import meta_file as mf, stages as s
from modules.object_status import Status as Obj_Status



#################################################################
# !!!Deprecated!!!
#    Will be prepared by the client
#    This is due to performance problems on IBM i
#################################################################
def create_compile_script(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:

  build_dir = stage_obj.build_dir
  new_release = meta_file.release_branch


  logging.debug(f"Change current directory to {build_dir}")
  logging.debug(sys.executable)

  run_sys_cmd(['echo', '$PATH'], build_dir)
  run_sys_cmd(['git', 'branch', '-a'], build_dir)
  run_sys_cmd(['git', 'checkout', constants.C_GIT_BRANCH_PRODUCTION], build_dir)
  run_sys_cmd(['git', 'pull'], build_dir)

  try:
    run_sys_cmd(['git', 'show-ref', '--verify', f"refs/heads/{new_release}"], build_dir)
    run_sys_cmd(['git', 'checkout', new_release], build_dir)
  except:
    run_sys_cmd(['git', 'checkout', '-b', new_release, meta_file.commit], build_dir)
    run_sys_cmd(['git', 'push', '--set-upstream', 'origin', new_release], build_dir)
  
  new_release_commit=run_sys_cmd(['git', 'show-ref', '--verify', f"refs/heads/{new_release}"], build_dir).split(" ", 1)[0]

  logging.debug(f"{new_release_commit=}, {meta_file.commit=}")
  if new_release_commit != meta_file.commit:
    raise Exception(f"Commit of release branch {new_release} ({new_release_commit}) does not match with commit of deployment ({meta_file.commit})")

  run_sys_cmd(['make/scripts/cleanup.sh', 'debug'], build_dir)
  run_sys_cmd(['make/scripts/reset.sh', 'debug'], build_dir)
  run_sys_cmd(['make/scripts/create_build_script.sh', 'create-object-list'], build_dir)
  run_sys_cmd(['make/scripts/create_build_script.sh', 'default'], build_dir)



def load_object_list(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:

  meta_file.current_running_stage = stage_obj
  
  build_dir = stage_obj.build_dir
  new_release = meta_file.release_branch

  reset_git_repo(build_dir)
  run_sys_cmd(['git', 'checkout', new_release], build_dir)
  run_sys_cmd(['git', 'reset', '--hard', f'origin/{new_release}'], build_dir)

  meta_file.import_objects_from_config_file()
  meta_file.write_meta_file()



@DeprecationWarning
def run_compile_script(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:
  build_dir = stage_obj.build_dir
  new_release = meta_file.release_branch
  commit_msg='Build successfully'

  run_sys_cmd(['pwd'], build_dir)

  reset_git_repo(build_dir)
  run_sys_cmd(['git', 'checkout', new_release], build_dir)
  run_sys_cmd(['git', 'reset', '--hard', f'origin/{new_release}'], build_dir)
  
  error = None
  try:
    run_sys_cmd(['tmp/compile.sh'], build_dir)
  except Exception as e:
    error = e
    logging.exception(e, stack_info=True)
    commit_msg='Build failed'

  update_compiled_object_status(meta_file, stage_obj)

  # List all changed objects
  run_sys_cmd(['find build/* -type f -daystart -mtime -1 | xargs ls -la'], build_dir, True)

  git_save_changes(meta_file, stage_obj, action)

  if error is not None:
    raise error




def git_save_changes(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action):

  commit_msg='Save deployment changes'

  build_dir = stage_obj.build_dir

  run_sys_cmd(['git', 'status'], build_dir)
  run_sys_cmd(['git', 'add', '-A'], build_dir)  
  run_sys_cmd([f'git diff-index --quiet HEAD || git commit -m "{commit_msg}"'], build_dir, True)
  run_sys_cmd(['git', 'push'], build_dir)





def update_compiled_object_status(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action):

  build_dir = stage_obj.build_dir

  with open(f"{build_dir}/{constants.C_COMPILED_OBJECT_LIST}", "r") as file:

    for compiled in file:

      if compiled == '':
        continue

      logging.debug(f"Import object: {compiled}")
      tmp = compiled.lower().rstrip('\r\n').rstrip('\n').split('|')
      obj=tmp[0]
      crt_date=tmp[1]
      prod_lib = obj.split("/")[0]
      prod_obj = obj.split("/")[1].split('.')

      if len(prod_obj) < 3:
        logging.warning(f"Object has less than 3 attributes. Will be skipped. {prod_obj=}")
        continue

      do = meta_file.deploy_objects.get_object(obj_lib=prod_lib, obj_name=prod_obj[0], obj_type=prod_obj[2])
      do.deploy_status = Obj_Status.FINISHED
      
      logging.debug(f"{do.get_dict()}")

  meta_file.write_meta_file()




def merge_results(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:
  build_dir = stage_obj.build_dir
  new_release = meta_file.release_branch

  reset_git_repo(build_dir)
  run_sys_cmd(['git', 'checkout', constants.C_GIT_BRANCH_PRODUCTION], build_dir)
  run_sys_cmd(['git', 'merge', new_release], build_dir)
  run_sys_cmd(['git', 'push'], build_dir)




def clean_current_commit(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:

  build_dir = stage_obj.build_dir
  new_release = meta_file.release_branch

  reset_git_repo(build_dir)
  run_sys_cmd(['git', 'checkout', new_release], build_dir)
  run_sys_cmd(['git', 'reset', '--hard', f'origin/{new_release}'], build_dir)




def reset_git_repo(build_dir):
  run_sys_cmd(['git', 'reset', '--hard', 'HEAD'], build_dir)
  run_sys_cmd(['git', 'clean', '-fd'], build_dir)
  run_sys_cmd(['git', 'checkout', constants.C_GIT_BRANCH_PRODUCTION], build_dir)
  run_sys_cmd(['git', 'pull'], build_dir)




def save_build_output(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:

  deployment_dir = os.path.dirname(os.path.realpath(meta_file.file_name))

  build_dir = stage_obj.build_dir
  save_dir=os.path.join(deployment_dir, 'outputs', datetime.datetime.now().strftime('%F %T.%f')[:-3])
  Path(save_dir).mkdir(parents=True)

  run_sys_cmd(['cp', '-Rt', save_dir, 'tmp', 'log', 'build-output'], build_dir)
  meta_file.deploy_objects.set_objects_status(Obj_Status.BUILDED)



def run_sys_cmd(cmd, cwd, shell_direct=False):

  print(cmd)
  logging.debug(f"{cmd=}")

  try:
    s=subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, shell=shell_direct, check=False) # executable='/bin/bash'
  except Exception as e:
    logging.error("Error on execute")
    logging.exception(e, stack_info=True)
    raise e

  stdout = s.stdout.decode(constants.C_CONVERT_FROM)
  stderr = s.stderr.decode(constants.C_CONVERT_FROM)
  print(f"{stdout=}")
  print(f"{stderr=}")
  print(f"{s.returncode=}")

  if s.returncode != 0:
    logging.error(f"Return code: {s.returncode}")
    logging.error(f"{stdout=}")
    logging.error(f"{stderr=}")
    raise Exception(f"{stderr=}; {stdout=}")

  return stdout

