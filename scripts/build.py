from __future__ import annotations
import os, logging, sys
import subprocess

sys.path.insert(0, os.path.realpath(os.path.dirname(__file__) + '/..'))

#################################################################

from etc import logger_config

from etc import constants
from modules import meta_file as mf



#################################################################
# !!!Deprecated!!!
#    Will be prepared by the client
#    This is due to performance problems on IBM i
#################################################################
def prepare_build(meta_file: mf.Meta_File, stage: str, processing_step:str) -> None:

  build_dir = meta_file.current_stages.get_stage(stage).build_dir
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



def load_object_list(meta_file: mf.Meta_File, stage: str, processing_step:str) -> None:

  build_dir = meta_file.current_stages.get_stage(stage).build_dir
  new_release = meta_file.release_branch

  reset_git_repo(build_dir)
  run_sys_cmd(['git', 'checkout', new_release], build_dir)
  run_sys_cmd(['git', 'reset', '--hard', f'origin/{new_release}'], build_dir)

  meta_file.import_objects_from_config_file(f"{build_dir}/build/{constants.C_GNU_MAKE_OBJECT_LIST}")
  meta_file.write_meta_file()



def run_build(meta_file: mf.Meta_File, stage: str, processing_step:str) -> None:
  build_dir = meta_file.current_stages.get_stage(stage).build_dir
  new_release = meta_file.release_branch
  commit_msg='Build successfully'

  reset_git_repo(build_dir)
  run_sys_cmd(['git', 'checkout', new_release], build_dir)
  run_sys_cmd(['git', 'reset', '--hard', f'origin/{new_release}'], build_dir)
  
  error = None
  try:
    run_sys_cmd(['tmp/compile.sh'], build_dir)
  except Exception as e:
    error = e
    logging.exception(e)
    commit_msg='Build failed'

  run_sys_cmd(['ls', '-la', 'build/prouzalib2'], build_dir)
  run_sys_cmd(['git', 'status'], build_dir)
  run_sys_cmd(['git', 'add', '-A'], build_dir)  
  run_sys_cmd(['git', 'commit', '-m', f'"{commit_msg}"'], build_dir)
  run_sys_cmd(['git', 'push'], build_dir)

  if error is not None:
    raise error
  


def merge_results(meta_file: mf.Meta_File, stage: str, processing_step:str) -> None:
  build_dir = meta_file.current_stages.get_stage(stage).build_dir
  new_release = meta_file.release_branch

  reset_git_repo(build_dir)
  run_sys_cmd(['git', 'checkout', constants.C_GIT_BRANCH_PRODUCTION], build_dir)
  run_sys_cmd(['git', 'merge', new_release], build_dir)
  run_sys_cmd(['git', 'push'], build_dir)



def reset_git_repo(build_dir):
  run_sys_cmd(['git', 'reset', '--hard', 'HEAD'], build_dir)
  run_sys_cmd(['git', 'clean', '-fd'], build_dir)
  run_sys_cmd(['git', 'checkout', constants.C_GIT_BRANCH_PRODUCTION], build_dir)
  run_sys_cmd(['git', 'pull'], build_dir)



def run_sys_cmd(cmd, cwd):

  print(cmd)
  s=subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, shell=False, check=False) # executable='/bin/bash'
  stdout = s.stdout.decode(constants.C_CONVERT_FROM)
  stderr = s.stderr.decode(constants.C_CONVERT_FROM)
  print(f"{stdout=}")
  print(f"{stderr=}")
  print(f"{s.returncode=}")

  if s.returncode != 0:
    logging.error(f"Return code: {s.returncode}")
    raise Exception(stderr)

  return stdout

