import os
import shlex
import signal
import subprocess
import logging
import sys
import time

from io import StringIO

from etc import constants
from modules import meta_file, output_capture, parallel_steps, placeholders, processing_job, scripts_loader
from modules import deploy_action as da
from modules import run_history
from modules import stages as s
from modules import action_type
from modules.cmd_status import Status as Cmd_Status

from modules.db import actions_data, processing_user_data, run_history_data


class Command_Exception(Exception):
    pass





class IBM_i_commands:


    def __init__(self, meta_file: meta_file.Meta_File):
        self.meta_file = meta_file




    def get_all_attributes(self, action:da.Deploy_Action) -> dict:
        dict = {
          'processing_step': action.processing_step,
          'stage': action.stage
        }

        dict['meta_file'] = self.meta_file.get_all_data_as_dict()

        return dict




    def run_commands(self, stage: s.Stage, processing_step: str=None, continue_run=True) -> None:

        logging.debug(f"Run Commands for {stage.name=} ({stage.id}), {processing_step=}")

        details = getattr(self.meta_file, 'run_details', {}).pop(stage.id, None)
        processing_user_data.create_action_log(action=action_type.Action_type.RUN_STAGE, meta_file=self.meta_file, stage=stage, details=details)
        stage.set_status('in process')

        from modules import hooks
        hooks.emit(hooks.Event.STAGE_STARTED, self.meta_file, stage)

        # Execute all from stage. A step can add further steps (e.g. object commands), also in front of the running one:
        # the list is read again after each step, the first step which hasn't run yet is next
        done = set()
        position = 0

        with parallel_steps.scope():

            while True:
                actions = stage.actions.get_actions(processing_step)
                # Usually the steps after the last one: only a step added in front makes it search from the beginning
                next_action = next((a for a in actions[position:] if id(a) not in done), None) or next((a for a in actions if id(a) not in done), None)
                if next_action is None:
                    break

                done.add(id(next_action))
                position = next(i for i, a in enumerate(actions) if a is next_action)
                self.execute_action(stage, next_action, continue_run)

        #iconv -f IBM-1252 -t utf-8 './logs/prouzalib/date.sqlrpgle.srvpgm.error.log' > './logs/prouzalib/date.sqlrpgle.srvpgm.error.log'_tmp && mv './logs/prouzalib/date.sqlrpgle.srvpgm.error.log'_tmp './logs/prouzalib/date.sqlrpgle.srvpgm.error.log' 



    def execute_action(self, stage: s.Stage, action: da.Deploy_Action, continue_run=True):
        """
        Runs a step. A step with `parallel` is only started: it's running when this function returns.
        See wait_for_parallel_actions, if something depends on its result.

        Raises:
            Command_Exception: If the step, or a parallel step before it, failed and has the error check on
        """

        scope = parallel_steps.current()

        if scope is not None and action.parallel:
            scope.start(action.parallel_group, lambda: self._run_action(stage, action, continue_run))
            return

        self.wait_for_parallel_actions()
        self._run_action(stage, action, continue_run)



    def wait_for_parallel_actions(self) -> None:
        """
        Waits until the parallel steps which have been started so far have ended.

        Raises:
            Command_Exception: If one of them failed and has the error check on
        """

        scope = parallel_steps.current()

        if scope is not None:
            scope.wait()



    def _run_action(self, stage: s.Stage, action: da.Deploy_Action, continue_run=True):

        executions = {
          da.Command_Type.QSYS: self.run_qsys_cmd,
          da.Command_Type.PASE: self.run_pase_cmd,
          da.Command_Type.SCRIPT: self.run_script_cmd,
        }

        if continue_run and (action.status == Cmd_Status.FINISHED or (action.status == Cmd_Status.FAILED and not action.check_error)):
            return

        # A job of the processing service which has been ended meanwhile doesn't run further steps
        processing_job.check_job_running()

        # Shown as running while it runs (docs/bugfixes/running-step-status-not-stored.md).
        # A step which stays `in process` after a crash is run again with `Continue`, like a new one.
        action.status = Cmd_Status.IN_PROCESS
        actions_data.save_action_status(action)

        start_time = time.perf_counter()
        execute_time = start_time

        try:
            cmd = action.cmd
            # The attributes contain the whole deployment, so only collect them if the command uses placeholders
            if '{' in cmd or '}' in cmd:
                cmd = placeholders.resolve(cmd, self.get_all_attributes(action), action.environment)

            logging.info(f"run {action.sequence=}, {cmd=}, {os.getcwd()=}")

            execute_time = time.perf_counter()
            rh = executions.get(action.environment)(stage, cmd, action)

        except Exception as e:

            logging.exception(e, stack_info=True)
            rh = run_history_data.create_new_run_history(action_id=action.id)
            rh.status = Cmd_Status.FAILED
            rh.stderr = str(e)

        #time.sleep(0.02)
        persist_time = time.perf_counter()
        action.run_history.append(rh)

        action.status = rh.status

        if action.environment == da.Command_Type.SCRIPT or action.id is None:
            # A script may change anything of the deployment (objects, sub-steps, custom data)
            self.meta_file.save()
        else:
            # A command only changes its step: only the step is written (docs/features/core-redesign.md, step 2)
            self.meta_file.save_step(action)

        failed = rh.status == Cmd_Status.FAILED and action.check_error

        end_time = time.perf_counter()
        logging.info(f"Action {action.id} ({action.environment.value}) took {end_time - start_time:.3f}s: "
                     f"prepare {execute_time - start_time:.3f}s, execute {persist_time - execute_time:.3f}s, save {end_time - persist_time:.3f}s")

        if failed:
            logging.exception(f"Error in action {action.sequence} of stage {stage.name}: {rh.stderr}")
            raise Command_Exception(rh.stderr)





    def run_script_cmd(self, stage: s.Stage, cmd: str, action: da.Deploy_Action) -> run_history.Run_History:

        #cmd='pre.pre_cmd'
        #pre.pre_cmd('test', 'xxx')
        logging.info(f"Going to run script {cmd}")

        obj = cmd.split('.')

        if len(obj) != 2:
            raise Command_Exception(f"Command '{cmd}' has not the correct format: 'filename.function_name' (without '.py' in filename)")

        rh = run_history_data.create_new_run_history(action_id=action.id)

        stdout_new = StringIO()
        stderr_new = StringIO()

        try:

            # Only the output of this thread: the web app runs other stages and requests at the same time
            with output_capture.capture(stdout_new, stderr_new):

                try:
                    # Only functions of scripts/ (docs/features/core-redesign.md, step 4)
                    func = scripts_loader.resolve(cmd)
                    logging.info(f"Run {str(func)}")

                    with parallel_steps.scope():
                        func(self.meta_file, stage, action)

                    rh.status = Cmd_Status.FINISHED

                except Exception as e:
                    print(str(e), file=sys.stderr)
                    logging.exception(e, stack_info=True)
                    rh.status = Cmd_Status.FAILED

        finally:
            # Capture the values while the buffers are still in scope
            rh.stdout = stdout_new.getvalue()
            rh.stderr = stderr_new.getvalue()

            # Optional: clean up buffers from memory
            stdout_new.close()
            stderr_new.close()

        return rh




    @staticmethod
    def end_process_group(process: subprocess.Popen) -> None:
        """Ends the command with its child processes. It may have ended just before."""

        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass



    @staticmethod
    def generate_ssh_cmd(stage: s.Stage, cmd: str) -> str:
        # BatchMode: fail instead of waiting for a password
        return f'ssh -o BatchMode=yes {shlex.quote(stage.host)} {shlex.quote(cmd)}'



    @staticmethod
    def generate_qsys_cmd(cmd: str, action: da.Deploy_Action) -> str:
        parameter = ''
        if action.run_in_new_job:
            parameter = 'S'

        # The exit code of the command decides, not the one of dspjoblog.
        # Not with `exit $rc`: a shell on IBM i can report -1 here, which isn't a valid value for `exit` in every shell.
        return f'(cl -{parameter}v {shlex.quote(cmd)}; rc=$?; cl -v "dspjoblog"; [ "$rc" -eq 0 ])'



    @staticmethod
    def is_execute_remote(stage: s.Stage, action: da.Deploy_Action):
        return (stage.execute_remote and action.execute_remote is None) or (action.execute_remote is not None and action.execute_remote)



    def run_qsys_cmd(self, stage: s.Stage, cmd: str, action: da.Deploy_Action) -> run_history.Run_History:

        logging.debug(f"Run QSYS: {cmd=}")
        cmd = IBM_i_commands.generate_qsys_cmd(cmd, action=action)

        if IBM_i_commands.is_execute_remote(stage, action):
            cmd = IBM_i_commands.generate_ssh_cmd(stage=stage, cmd=cmd)
            logging.debug(f"Run QSYS on remote: {cmd=}")

        return self.run_pase_cmd(stage, cmd, action)




    def run_pase_cmd(self, stage: s.Stage, cmd: str, action: da.Deploy_Action) -> run_history.Run_History:

        logging.debug(f"{cmd=}; {stage.build_dir=}; {action.cwd=}; {os.getcwd()=}")

        timeout = action.timeout_seconds if action.timeout_seconds is not None else constants.C_COMMAND_TIMEOUT_SECONDS

        timed_out = False

        # In its own session, to be able to end the command together with its child processes
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, cwd=action.cwd or stage.build_dir, stderr=subprocess.PIPE, shell=True, executable='/bin/bash', start_new_session=True) as process:

            try:
                stdout, stderr = process.communicate(timeout=timeout or None)

            except subprocess.TimeoutExpired:
                timed_out = True
                IBM_i_commands.end_process_group(process)
                stdout, stderr = process.communicate()

            except BaseException:
                # E.g. the run is ended: the command must not keep running
                IBM_i_commands.end_process_group(process)
                raise

        # Output of IBM i commands isn't always UTF-8. That must not fail the step or lose its output
        stdout = stdout.decode('utf-8', errors='replace')
        stderr = stderr.decode('utf-8', errors='replace')

        if timed_out:
            stderr += f"Command ended: timeout after {timeout} seconds\n"

        rh = run_history_data.create_new_run_history(action_id=action.id)

        rh.stdout = stdout
        rh.stderr = stderr

        rh.status = Cmd_Status.FINISHED

        if timed_out or process.returncode != 0 or (stderr != '' and action.fail_on_stderr is not False):
            rh.status = Cmd_Status.FAILED

        return rh
