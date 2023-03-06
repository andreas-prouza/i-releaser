from __future__ import annotations
import os
import subprocess
import logging
import json
import sys

from io import StringIO

from etc import constants
from modules import meta_file
from modules import deploy_action as da
from modules import run_history as rh
from modules import stages as s

from scripts import *


class Command_Exception(Exception):
  pass



class IBM_i_commands:

  def __init__(self, meta_file: meta_file.Meta_File):
    self.meta_file = meta_file



  def set_cmds(self, stage: str, stage_cmds: str=constants.C_STAGE_COMMANDS):
    """Set all commands which are allowed for this stage

    Args:
        stage (str): Name of stage
    """

    cmd_mapping = {
      da.Processing_Step.PRE:
        [
          pre.pre_cmd
        ],
      da.Processing_Step.POST:
        [
        ],
      da.Processing_Step.SAVE: 
        [
          save_objects.set_init_cmds_for_save, 
          save_objects.set_cmd_object_to_savf
        ],
      da.Processing_Step.TRANSFER:
        [
          transfer.set_cmd_transfer_to_target
        ],
      da.Processing_Step.TARGET_PREPARE:
        [
          target_prepare.set_init_cmds_for_deployment
        ],
      da.Processing_Step.BACKUP_OLD_OBJ:
        [
        #  backup.set_cmd_backup_objects_on_target
        ],
      da.Processing_Step.PERFORM_DEPLOYMENT:
        [
          target_deployment.set_cmd_restore_objects_on_target
        ]
      }
    
    with open(stage_cmds, "r") as file:
      stage_cmds = json.load(file)

    do_steps = self.meta_file.current_stages.get_stage(stage).processing_steps
    actions = self.meta_file.actions

    for k, v in cmd_mapping.items():

      if k.value not in do_steps:
        continue

      for cmd in v:
        # All script function have the same structur: function(metafile, stage)
        cmd(self.meta_file, stage)

      for sc in stage_cmds:
        if len(sc['stages']) == 0 or stage in sc['stages'] and k.value == sc['processing_step']:
          actions.add_action_cmd(cmd=sc['cmd'], environment=sc['environment'], 
                processing_step=sc['processing_step'], stage=stage, check_error=sc['check_error'])



  def get_all_attributes(self, processing_step: str=None, stage: str=None) -> {}:
    dict = {
      'processing_step': processing_step,
      'stage': s.Stage.get_stage(stage).get_dict()
    }

    dict['meta_file'] = self.meta_file.get_all_data_as_dict()

    return dict



  def run_commands(self, processing_step: str=None, stage: str=None) -> None:

    executions = {
      da.Command_Type.QSYS: self.run_qsys_cmd,
      da.Command_Type.PASE: self.run_pase_cmd,
      da.Command_Type.SCRIPT: self.run_script_cmd,
    }
    all_attributes = self.get_all_attributes(processing_step=processing_step, stage=stage)

    self.meta_file.current_stages.get_stage(stage).set_status('in process')

    for action in self.meta_file.get_actions(processing_step=processing_step, stage=stage):

      cmd = action.cmd.format(**all_attributes)

      print(f"run {cmd}")
      run_history = executions.get(action.environment)(cmd, action)
      action.run_history.add_history(run_history)

      if run_history.status == 'failed' and action.check_error:
        self.meta_file.current_stages.get_stage(action.stage).set_status('failed')
        self.meta_file.write_meta_file()
        raise Command_Exception(run_history.stderr)
    
    self.meta_file.current_stages.get_stage(stage).set_status('finished')
    self.meta_file.write_meta_file()

    #iconv -f IBM-1252 -t utf-8 './logs/prouzalib/date.sqlrpgle.srvpgm.error.log' > './logs/prouzalib/date.sqlrpgle.srvpgm.error.log'_tmp && mv './logs/prouzalib/date.sqlrpgle.srvpgm.error.log'_tmp './logs/prouzalib/date.sqlrpgle.srvpgm.error.log' 



  def run_script_cmd(self, cmd: str, action: da.Deploy_Action) -> Run_History:
    
    #cmd='pre.pre_cmd'
    #pre.pre_cmd('test', 'xxx')
    logging.info(f"Going to run script {cmd}")
    
    obj = cmd.split('.')
    
    if len(obj) != 2:
      raise Command_Exception(f"Command '{cmd}' has not the correct format: 'filename.function_name' (without '.py' in filename)")
    
    run_history = rh.Run_History()

    stdout_orig = sys.stdout
    stdout_new = StringIO()
    sys.stdout = stdout_new
    stderr_orig = sys.stderr
    sys.stderr = stderr_new = StringIO()
    
    try:
      func = getattr(globals()[obj[0]], obj[1])
      func(self.meta_file, action.stage)
      run_history.status = 'finished'

    except Exception as e:
      print(repr(e), file=sys.stderr)
      logging.exception(e)
      run_history.status = 'failed'

    run_history.stdout = stdout_new.getvalue()
    run_history.stderr = stderr_new.getvalue()
    
    sys.stdout = stdout_orig
    sys.stderr = stderr_orig

    return run_history

    


  def run_qsys_cmd(self, cmd: str, action: da.Deploy_Action) -> Run_History:
    
    cmd = f'(cl -v "{cmd}"; cl -v "dspjoblog")'
    return self.run_pase_cmd(cmd, action)
    


  def run_pase_cmd(self, cmd: str, action: da.Deploy_Action) -> Run_History:
      s=subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, check=False, executable='/bin/bash')
      stdout = s.stdout
      stderr = s.stderr

      if constants.C_CONVERT_OUTPUT:
        stdout = stdout.decode(constants.C_CONVERT_FROM)
        stderr = stderr.decode(constants.C_CONVERT_FROM)

      run_history = rh.Run_History()
      
      run_history.stdout = stdout
      run_history.stderr = stderr

      run_history.status = 'finished'

      if s.returncode != 0:
        run_history.status = 'failed'

      return run_history
