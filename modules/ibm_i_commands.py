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




    def get_all_attributes(self, action:da.Deploy_Action) -> {}:
        dict = {
          'processing_step': action.processing_step,
          'stage': action.stage
        }

        dict['meta_file'] = self.meta_file.get_all_data_as_dict()

        return dict



    def run_commands(self, stage: s.Stage, processing_step: str=None, continue_run=True) -> None:

        logging.debug(f"Run Commands for {stage.name=} ({stage.id}), {processing_step=}")

        stage.processing_users.append({'user': self.meta_file.current_user, 'timestamp' : str(datetime.datetime.now()), 'action' : s.Actions.RUN_STAGE.value})
        stage.set_status('in process')

        # Execute all from stage
        i=0
        while i < len(stage.actions.get_actions(processing_step)):
            actions = stage.actions.get_actions(processing_step)
            self.execute_action(stage, actions[i], continue_run)
            i += 1

        # should be set on a higher level because of multiple processing_steps to run
        #self.meta_file.open_stages.get_stage(stage).set_status('finished')
        self.meta_file.write_meta_file()

        #iconv -f IBM-1252 -t utf-8 './logs/prouzalib/date.sqlrpgle.srvpgm.error.log' > './logs/prouzalib/date.sqlrpgle.srvpgm.error.log'_tmp && mv './logs/prouzalib/date.sqlrpgle.srvpgm.error.log'_tmp './logs/prouzalib/date.sqlrpgle.srvpgm.error.log'



    def execute_action(self, stage: s.Stage, action: da.Deploy_Action, continue_run=True):

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

        original_dir=os.getcwd()

        try:

            if stage.build_dir is not None:
                os.chdir(stage.build_dir)

            run_history = executions.get(action.environment)(stage, cmd, action)

        except Exception as e:

            logging.exception(e, stack_info=True)
            run_history = rh.Run_History()
            run_history.status = Cmd_Status.FAILED
            run_history.stderr = str(e)

        os.chdir(original_dir)

        #time.sleep(0.02)
        action.run_history.add_history(run_history)

        action.status = run_history.status

        if run_history.status == Cmd_Status.FAILED and action.check_error:
            stage.set_status(run_history.status)
            self.meta_file.write_meta_file()
            raise Command_Exception(run_history.stderr)

        self.meta_file.write_meta_file()





    def run_script_cmd(self, stage: s.Stage, cmd: str, action: da.Deploy_Action) -> rh.Run_History:

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
            logging.info(f"Run {str(func)}")
            func(self.meta_file, stage, action)
            run_history.status = Cmd_Status.FINISHED

        except Exception as e:
            print(str(e), file=sys.stderr)
            logging.exception(e, stack_info=True)
            run_history.status = Cmd_Status.FAILED

        run_history.stdout = stdout_new.getvalue()
        run_history.stderr = stderr_new.getvalue()

        sys.stdout = stdout_orig
        sys.stderr = stderr_orig
        logging.getLogger().removeHandler(hdl)

        return run_history




    def generate_ssh_cmd(stage: s.Stage, cmd: str) -> str:
        cmd = cmd.replace('"', '\\"')
        return f'ssh "{stage.host}" "{cmd}"'



    def generate_qsys_cmd(cmd: str, action: da.Deploy_Action) -> str:
        parameter = ''
        if action.run_in_new_job:
            parameter = 'S'

        return f'(cl -{parameter}v "{cmd}"; cl -v "dspjoblog")'



    def is_execute_remote(stage: s.Stage, action: da.Deploy_Action):
        return (stage.execute_remote and action.execute_remote is None) or (action.execute_remote is not None and action.execute_remote)



    def run_qsys_cmd(self, stage: s.Stage, cmd: str, action: da.Deploy_Action) -> Run_History:

        logging.debug(f"Run QSYS: {cmd=}")
        cmd = IBM_i_commands.generate_qsys_cmd(cmd, action=action)

        if IBM_i_commands.is_execute_remote(stage, action):
            cmd = IBM_i_commands.generate_ssh_cmd(stage=stage, cmd=cmd)
            logging.debug(f"Run QSYS on remote: {cmd=}")

        return self.run_pase_cmd(stage, cmd, action)



    def run_pase_cmd(self, stage: s.Stage, cmd: str, action: da.Deploy_Action) -> Run_History:

        logging.debug(f"{cmd=}; {stage.build_dir=}; ")

        s=subprocess.run(cmd, stdout=subprocess.PIPE, cwd=stage.build_dir, stderr=subprocess.PIPE, shell=True, check=False, executable='/bin/bash')
        stdout = s.stdout
        stderr = s.stderr

        stdout = stdout.decode('utf-8')
        stderr = stderr.decode('utf-8')

        run_history = rh.Run_History()

        run_history.stdout = stdout
        run_history.stderr = stderr

        run_history.status = Cmd_Status.FINISHED

        if s.returncode != 0 or stderr != '':
            run_history.status = Cmd_Status.FAILED

        return run_history
