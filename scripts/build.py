from __future__ import annotations
import os, logging, sys
import subprocess

sys.path.insert(0, os.path.realpath(os.path.dirname(__file__) + '/..'))

#################################################################

from etc import logger_config

from etc import constants
from modules import meta_file as mf



def prepare_build(meta_file: mf.Meta_File, stage: str, processing_step:str) -> None:

  build_dir = meta_file.current_stages.get_stage(stage).build_dir
  new_release = constants.C_GIT_BRANCH_RELEASE.replace('{deploy_version}', str(meta_file.deploy_version))

  original_dir=os.getcwd()
  os.chdir(build_dir)

  run_sys_cmd(['git', 'checkout', constants.C_GIT_BRANCH_PRODUCTION])
  run_sys_cmd(['git', 'pull'])

  try:
    run_sys_cmd(['git', 'show-ref', '--verify', f"refs/heads/{new_release}"])
    run_sys_cmd(['git', 'checkout', new_release])
  except:
    run_sys_cmd(['git', 'checkout', '-b', new_release, meta_file.commit])
  
  new_release_commit=run_sys_cmd(['git', 'show-ref', '--verify', f"refs/heads/{new_release}"]).split(" ", 1)[0]


  logging.debug(f"{new_release_commit=}, {meta_file.commit=}")
  if new_release_commit != meta_file.commit:
    raise Exception(f"Commit of release branch {new_release} ({new_release_commit}) does not match with commit of deployment ({meta_file.commit})")

  run_sys_cmd(['make/scripts/cleanup.sh', 'debug'])
  run_sys_cmd(['make/scripts/reset.sh', 'debug'])
  run_sys_cmd(['make/scripts/create_build_script.sh', 'create-object-list'])
  run_sys_cmd(['make/scripts/create_build_script.sh', 'default'])




def run_sys_cmd(cmd):

  print(cmd)
  s=subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
  stdout = s.stdout.decode(constants.C_CONVERT_FROM)
  stderr = s.stderr.decode(constants.C_CONVERT_FROM)
  print(stdout)

  if s.returncode != 0:
    raise Exception(stderr)

  return stdout

