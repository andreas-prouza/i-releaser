from __future__ import annotations
import os
import subprocess
import logging
import json
import sys
import time, datetime

from io import StringIO

from etc import constants
from modules import meta_file
from modules import deploy_action as da
from modules import run_history as rh
from modules import stages as s
from modules.cmd_status import Status as Cmd_Status

from scripts import *


class Command_Exception(Exception):
  pass





class IBM_i_commands:


  def __init__(self, meta_file: meta_file.Meta_File):
    self.meta_file = meta_file


  @DeprecationWarning
  def set_cmds(self, stage: str):
    """Set all commands which are allowed for this stage

    Args:
        stage (str): Name of stage

    Deprecated: This job will be done in Stage-Class
    """

    #get all processing steps for given stage
    do_steps = self.meta_file.stages.get_stage(stage).processing_steps
    actions = self.meta_file.actions
    actions = self.meta_file.stages.get_stage(stage).actions

    wf_steps = self.meta_file.workflow.get_workflow_steps_mapping()

    all_steps = {x['processing_step']:x for x in wf_steps}.values()

    for step in do_steps:

      for all_step in all_steps:
        if step == all_step['processing_step']:
          actions.add_action_cmd(cmd=all_step['execute'], environment=da.Command_Type(all_step['environment']), 
                processing_step=all_step['processing_step'], stage=stage, check_error=all_step['check_error'])
          break



  def get_all_attributes(self, action:da.Deploy_Action) -> {}:
    dict = {
      'processing_step': action.processing_step,
      'stage': action.stage
    }

    dict['meta_file'] = self.meta_file.get_all_data_as_dict()

    return dict



  def run_commands(self, stage: s.Stage, processing_step: str=None, continue_run=False) -> None:

    logging.debug(f"Run Commands for {stage.name=}, {processing_step=}")

    stage.processing_users.append({'user': self.meta_file.current_user, 'timestamp' : str(datetime.datetime.now()), 'action' : s.Actions.RUN_STAGE.value})
    stage.set_status('in process')

    #action = self.meta_file.get_next_open_action(processing_step=processing_step, stage=stage)

    # Execute all from stage
    for action in stage.actions.get_actions(processing_step=processing_step):
      self.execute_action(stage, action, continue_run)

    # Execute all from object
    #object_commands = self.meta_file.deploy_objects.get_actions(processing_step=processing_step, stage=stage.name)
    #for action in object_commands:
    #  self.execute_action(stage, action, continue_run)
    
    # should be set on a higher level because of multiple processing_steps to run
    #self.meta_file.open_stages.get_stage(stage).set_status('finished')
    self.meta_file.write_meta_file()

    #iconv -f IBM-1252 -t utf-8 './logs/prouzalib/date.sqlrpgle.srvpgm.error.log' > './logs/prouzalib/date.sqlrpgle.srvpgm.error.log'_tmp && mv './logs/prouzalib/date.sqlrpgle.srvpgm.error.log'_tmp './logs/prouzalib/date.sqlrpgle.srvpgm.error.log' 



  def execute_action(self, stage: s.Stage, action: da.Deploy_Action, continue_run=False):

    executions = {
      da.Command_Type.QSYS: self.run_qsys_cmd,
      da.Command_Type.PASE: self.run_pase_cmd,
      da.Command_Type.SCRIPT: self.run_script_cmd,
    }

    if continue_run and action.status == Cmd_Status.FINISHED or (action.status == Cmd_Status.FAILED and not action.check_error):
      return

    all_attributes = self.get_all_attributes(action)

    cmd = action.cmd.format(**all_attributes)

    logging.info(f"run {action.sequence=}, {cmd=}")
    run_history = executions.get(action.environment)(cmd, action)
    #time.sleep(0.02)
    action.run_history.add_history(run_history)

    action.status = run_history.status

    if run_history.status == Cmd_Status.FAILED and action.check_error:
      stage.set_status(run_history.status)
      self.meta_file.write_meta_file()
      raise Command_Exception(run_history.stderr)
      
    self.meta_file.write_meta_file()





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

    hdl = logging.StreamHandler(stream=stdout_new)
    logging.getLogger().addHandler(hdl)
    
    try:
      func = getattr(globals()[obj[0]], obj[1])
      func(self.meta_file, action.stage, action.processing_step)
      run_history.status = Cmd_Status.FINISHED

    except Exception as e:
      print(str(e), file=sys.stderr)
      logging.exception(e)
      run_history.status = Cmd_Status.FAILED

    run_history.stdout = stdout_new.getvalue()
    run_history.stderr = stderr_new.getvalue()
    
    sys.stdout = stdout_orig
    sys.stderr = stderr_orig
    logging.getLogger().removeHandler(hdl)

    return run_history

    


  def run_qsys_cmd(self, cmd: str, action: da.Deploy_Action) -> Run_History:
    
    cmd = f'(cl -vS "{cmd}"; cl -v "dspjoblog")'
    return self.run_pase_cmd(cmd, action)
    


  def run_pase_cmd(self, cmd: str, action: da.Deploy_Action) -> Run_History:
      s=subprocess.run(cmd, stdout=subprocess.PIPE, cwd=self.meta_file.current_running_stage.build_dir, stderr=subprocess.PIPE, shell=True, check=False, executable='/bin/bash')
      stdout = s.stdout
      stderr = s.stderr

      if constants.C_CONVERT_OUTPUT:
        stdout = stdout.decode(constants.C_CONVERT_FROM)
        stderr = stderr.decode(constants.C_CONVERT_FROM)

      run_history = rh.Run_History()
      
      run_history.stdout = stdout
      run_history.stderr = stderr

      run_history.status = Cmd_Status.FINISHED

      if s.returncode != 0 or stderr != '':
        run_history.status = Cmd_Status.FAILED

      return run_history
