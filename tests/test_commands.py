"""Commands of steps: quoting, placeholders, output, timeouts, error handling"""
import logging, os, shutil, stat, subprocess, sys, tempfile, threading, time, unittest
from types import SimpleNamespace
from unittest.mock import patch

from etc import constants
# Before meta_file (circular import)
from modules import deploy_version
from modules import files, ibm_i_commands, meta_file, placeholders, workflow
from modules import deploy_action as da
from modules.cmd_status import Status as Cmd_Status
from modules.db import app_sqlite, meta_file_data
from modules.ibm_i_commands import IBM_i_commands
from modules.meta_file_status import Meta_file_status


ATTRIBUTES = {
    'stage': 'STAGE 1',
    'processing_step': 'pre',
    'meta_file': {
        'general': {'project': 'erp', 'deploy_version': 42, 'commit': 'abc123', 'object_list': None},
        'deploy_libs': {'main_lib': 'd000000042'},
        'custom_data': {'ticket': 'ABC-1', 'evil': "x; touch /tmp/pwned", 'quote': "it's", 'list': ['a', 'b'], 'dollar': '$ORDERS'},
    },
}


def resolve(cmd: str, environment=da.Command_Type.PASE) -> str:
    return placeholders.resolve(cmd, ATTRIBUTES, environment)



def run_shell(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, executable='/bin/bash', capture_output=True, text=True).stdout



class TestPlaceholders(unittest.TestCase):


    def test_other_braces_stay(self):

        for cmd in ["awk '{print $1}' file", 'echo ${HOME}', 'for i in {1..3}; do echo $i; done', 'echo {unknown}', '{meta_file.__class__}']:
            self.assertEqual(resolve(cmd), cmd)


    def test_literal_braces(self):
        self.assertEqual(resolve("awk '{{print $1}}'"), "awk '{print $1}'")
        self.assertEqual(resolve('{{{stage}}}'), "{'STAGE 1'}")


    def test_values(self):
        self.assertEqual(resolve('echo {meta_file[general][project]} {meta_file[deploy_libs][main_lib]}'), 'echo erp d000000042')
        self.assertEqual(resolve('echo {meta_file[custom_data][list][1]}'), 'echo b')
        self.assertEqual(resolve('echo {meta_file[general][deploy_version]}', da.Command_Type.QSYS), 'echo 42')


    def test_unknown_value_fails(self):
        with self.assertRaises(placeholders.Invalid_Placeholder_Exception):
            resolve('echo {meta_file[general][file_name]}')


    def test_pase_value_can_not_change_the_command(self):

        marker = os.path.join(tempfile.mkdtemp(), 'pwned')
        ATTRIBUTES['meta_file']['custom_data']['evil'] = f"x; touch {marker}"

        for template in ['echo {meta_file[custom_data][evil]}', "echo '{meta_file[custom_data][evil]}'", 'echo "{meta_file[custom_data][evil]}"']:
            self.assertEqual(run_shell(resolve(template)).strip(), f"x; touch {marker}", template)
            self.assertFalse(os.path.exists(marker))


    def test_pase_value_with_quotes(self):

        for template in ['echo {meta_file[custom_data][quote]}', "echo '{meta_file[custom_data][quote]}'", 'echo "{meta_file[custom_data][quote]}"']:
            self.assertEqual(run_shell(resolve(template)).strip(), "it's", template)


    def test_pase_value_in_double_quotes_is_not_expanded(self):
        self.assertEqual(run_shell(resolve('echo "{meta_file[custom_data][dollar]}"')).strip(), '$ORDERS')


    def test_qsys_rejects_unsafe_values(self):

        self.assertEqual(resolve('CRTLIB {meta_file[custom_data][ticket]}', da.Command_Type.QSYS), 'CRTLIB ABC-1')

        for name in ['evil', 'quote']:
            with self.assertRaises(placeholders.Invalid_Placeholder_Exception):
                resolve(f"CRTLIB {{meta_file[custom_data][{name}]}}", da.Command_Type.QSYS)


    def test_qsys_allows_system_values_with_spaces(self):
        self.assertEqual(resolve("CHGVAR VAR('{stage}')", da.Command_Type.QSYS), "CHGVAR VAR('STAGE 1')")



class TestShellQuoting(unittest.TestCase):

    COMMANDS = ['CRTDUPOBJ OBJ($ORDERS) NEWOBJ(#ORD@1)', 'CHGVAR "a b"', "SNDMSG MSG('it''s')", 'A `date` B', r'X\Y $(id)']


    def setUp(self):

        self.bin_dir = tempfile.mkdtemp()
        self.output = os.path.join(self.bin_dir, 'output')

        # Replaces cl and ssh: writes the command, or runs it with the shell of the remote system
        for name, content in [('cl', f'#!/bin/bash\nif [ "$2" != "dspjoblog" ]; then printf "%s\\n" "$2" >> {self.output}; fi\n'),
                              ('ssh', '#!/bin/bash\nshift 3\nsh -c "$1"\n')]:
            path = os.path.join(self.bin_dir, name)
            with open(path, 'w') as f:
                f.write(content)
            os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)

        self.env = {**os.environ, 'PATH': f"{self.bin_dir}:{os.environ['PATH']}"}


    def tearDown(self):
        shutil.rmtree(self.bin_dir)


    def run_command(self, cmd: str) -> str:

        if os.path.exists(self.output):
            os.remove(self.output)

        subprocess.run(cmd, shell=True, executable='/bin/bash', env=self.env, check=True)

        with open(self.output) as f:
            return f.read().rstrip('\n')


    def test_command_reaches_cl_unchanged(self):

        action = SimpleNamespace(run_in_new_job=False)

        for command in self.COMMANDS:
            self.assertEqual(self.run_command(IBM_i_commands.generate_qsys_cmd(command, action)), command)


    def test_command_reaches_cl_unchanged_through_ssh(self):

        action = SimpleNamespace(run_in_new_job=False)
        stage = SimpleNamespace(host='prod400')

        for command in self.COMMANDS:
            self.assertEqual(self.run_command(IBM_i_commands.generate_ssh_cmd(stage, IBM_i_commands.generate_qsys_cmd(command, action))), command)


    def test_ssh_does_not_wait_for_a_password(self):
        self.assertIn('BatchMode=yes', IBM_i_commands.generate_ssh_cmd(SimpleNamespace(host='prod400'), 'ls'))



WORKFLOW = {
    'name': 'commands_wf',
    'default_project': 'commands',
    'step_action': [{'processing_step': 'step', 'environment': 'PASE', 'execute': 'echo ok', 'check_error': True}],
    'stages': [{'name': 'START', 'processing_steps': ['step'], 'next_stages': ['END']}, {'name': 'END', 'processing_steps': ['step']}],
}



class Database_Test(unittest.TestCase):


    def setUp(self):

        self.tmp_dir = tempfile.mkdtemp()
        self.db_file = os.path.join(self.tmp_dir, 'app.sqlite')

        self.db_defaults = app_sqlite.get_db_connection.__defaults__
        app_sqlite.get_db_connection.__defaults__ = (self.db_file,)
        app_sqlite.create_tables(self.db_file)

        self.patches = [
            patch.object(constants, 'C_META_DIR', os.path.join(self.tmp_dir, 'meta', '{project}', '{create_date}', '{deploy_version}')),
            patch.object(workflow.Workflow, 'get_workflow_by_name', return_value=workflow.Workflow(dict=WORKFLOW)),
            patch.object(workflow.Workflow, 'get_default_step_mapping', return_value=[]),
        ]
        for p in self.patches:
            p.start()

        self.mf = meta_file_data.create_new_meta_file('commands_wf')
        self.mf.set_status(Meta_file_status.READY)


    def tearDown(self):

        for p in reversed(self.patches):
            p.stop()

        app_sqlite.get_db_connection.__defaults__ = self.db_defaults
        shutil.rmtree(self.tmp_dir)


    def run_step(self, environment=da.Command_Type.PASE, **kwargs) -> da.Deploy_Action:

        stage = self.mf.get_stages_by_name('START')[0]
        action = stage.actions.add_action_cmd(environment=environment, processing_step='step', stage='START', **kwargs)
        self.mf.save()

        try:
            IBM_i_commands(self.mf).execute_action(stage, action, continue_run=False)
        except ibm_i_commands.Command_Exception:
            pass

        return action



class TestQsysExitCode(Database_Test):


    def setUp(self):

        super().setUp()

        self.bin_dir = os.path.join(self.tmp_dir, 'bin')
        os.makedirs(self.bin_dir)

        # Replaces cl and ssh. `EXIT n` is a command which ends with this exit code, without output on stderr.
        for name, content in [('cl', '#!/bin/bash\nif [ "$2" = "dspjoblog" ]; then echo "Job log"; exit ${JOBLOG_EXIT:-0}; fi\nexit ${2#EXIT }\n'),
                              ('ssh', '#!/bin/bash\nshift 3\nsh -c "$1"\n')]:
            path = os.path.join(self.bin_dir, name)
            with open(path, 'w') as f:
                f.write(content)
            os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)

        env = patch.dict(os.environ, {'PATH': f"{self.bin_dir}:{os.environ['PATH']}"})
        env.start()
        self.addCleanup(env.stop)


    def run_qsys(self, cmd: str, **kwargs) -> da.Deploy_Action:
        return self.run_step(da.Command_Type.QSYS, cmd=cmd, **kwargs)


    def test_successful_command(self):
        self.assertEqual(self.run_qsys('EXIT 0').status, Cmd_Status.FINISHED)


    def test_failed_command_without_stderr(self):

        for exit_code in [1, 255]:
            self.assertEqual(self.run_qsys(f'EXIT {exit_code}').status, Cmd_Status.FAILED)


    def test_only_the_exit_code_decides_without_fail_on_stderr(self):

        self.assertEqual(self.run_qsys('EXIT 1', fail_on_stderr=False).status, Cmd_Status.FAILED)
        self.assertEqual(self.run_qsys('EXIT 0', fail_on_stderr=False).status, Cmd_Status.FINISHED)


    def test_exit_code_reaches_the_step_through_ssh(self):

        self.mf.get_stages_by_name('START')[0].host = 'prod400'

        self.assertEqual(self.run_qsys('EXIT 1', execute_remote=True).status, Cmd_Status.FAILED)
        self.assertEqual(self.run_qsys('EXIT 0', execute_remote=True).status, Cmd_Status.FINISHED)


    def test_job_log_of_a_failed_command_is_stored(self):

        action = self.run_qsys('EXIT 1')

        self.assertIn('Job log', files.readFile(action.run_history[-1].stdout.removeprefix('file://')))


    def test_failed_job_log_does_not_fail_the_step(self):

        with patch.dict(os.environ, {'JOBLOG_EXIT': '1'}):
            self.assertEqual(self.run_qsys('EXIT 0').status, Cmd_Status.FINISHED)



class TestStepResult(Database_Test):


    def test_invalid_utf8_keeps_the_output(self):

        action = self.run_step(cmd=r"printf 'a\344b\n'")

        self.assertEqual(action.status, Cmd_Status.FINISHED)
        self.assertIn('a�b', action.run_history[0].stdout if not action.run_history[0].stdout.startswith('file://') else open(action.run_history[0].stdout[7:], encoding='utf-8').read())


    def test_invalid_utf8_on_stderr_with_error(self):

        action = self.run_step(cmd=r"printf 'a\344b\n' >&2; exit 1")

        self.assertEqual(action.status, Cmd_Status.FAILED)
        self.assertTrue(action.run_history[0].stderr)


    def test_stderr_fails_by_default(self):
        self.assertEqual(self.run_step(cmd='echo warn >&2; exit 0').status, Cmd_Status.FAILED)


    def test_stderr_can_be_ignored(self):

        action = self.run_step(cmd='echo warn >&2; exit 0', fail_on_stderr=False)

        self.assertEqual(action.status, Cmd_Status.FINISHED)
        self.assertTrue(action.run_history[0].stderr)


    def test_exit_code_still_fails(self):
        self.assertEqual(self.run_step(cmd='exit 1', fail_on_stderr=False).status, Cmd_Status.FAILED)


    def test_options_are_stored(self):

        action = self.run_step(cmd='echo 1', fail_on_stderr=False, timeout_seconds=7)
        stage = meta_file_data.get_meta_file_by_id(self.mf.id).get_stages_by_name('START')[0]
        stored = next(a for a in stage.actions if a.id == action.id)

        self.assertIn(stored.fail_on_stderr, [False, 0])
        self.assertEqual(stored.timeout_seconds, 7)


    def test_timeout(self):

        marker = f"sleep 87{os.getpid() % 1000}"
        start = time.time()
        action = self.run_step(cmd=f"{marker} & wait", timeout_seconds=1)

        self.assertLess(time.time() - start, 5)
        self.assertEqual(action.status, Cmd_Status.FAILED)

        stderr = action.run_history[0].stderr
        stderr = open(stderr[7:], encoding='utf-8').read() if stderr.startswith('file://') else stderr
        self.assertIn('timeout after 1 seconds', stderr)

        self.assertEqual(subprocess.run(['pgrep', '-f', marker], capture_output=True, text=True).stdout.split(), [])


    def test_default_timeout(self):

        with patch.object(constants, 'C_COMMAND_TIMEOUT_SECONDS', 1):
            self.assertEqual(self.run_step(cmd='sleep 10').status, Cmd_Status.FAILED)


    def test_command_in_time_is_not_affected(self):
        self.assertEqual(self.run_step(cmd='echo ok', timeout_seconds=30).status, Cmd_Status.FINISHED)


    def test_workflow_accepts_the_options(self):

        definition = {**WORKFLOW, 'step_action': [{**WORKFLOW['step_action'][0], 'fail_on_stderr': False, 'timeout_seconds': 5}]}

        with patch.object(workflow.Workflow, 'get_default_step_mapping', return_value=[]):
            workflow.Workflow.validate_workflow(definition, 'test.json')

            stage = meta_file.s.Stage.get_stage_from_workflow(workflow.Workflow(dict=definition), 'START')

        self.assertEqual(stage.actions[0].fail_on_stderr, False)
        self.assertEqual(stage.actions[0].timeout_seconds, 5)


    def test_run_all_also_runs_failed_steps_without_error_check(self):

        stage = self.mf.get_stages_by_name('START')[0]
        action = stage.actions.add_action_cmd(cmd='echo again', environment=da.Command_Type.PASE, processing_step='step', stage='START', check_error=False)
        action.status = Cmd_Status.FAILED
        self.mf.save()

        IBM_i_commands(self.mf).execute_action(stage, action, continue_run=True)
        self.assertEqual(action.status, Cmd_Status.FAILED)

        IBM_i_commands(self.mf).execute_action(stage, action, continue_run=False)
        self.assertEqual(action.status, Cmd_Status.FINISHED)


    def test_unknown_placeholder_fails_the_step_only(self):

        action = self.run_step(cmd='echo {meta_file[general][doesnotexist]}')

        self.assertEqual(action.status, Cmd_Status.FAILED)



def noisy_script(name: str):

    def script(meta_file, stage_obj, action):
        for i in range(1000):
            print(f"{name} print")
            logging.info(f"{name} log")

    return script



class TestScriptOutput(Database_Test):


    def setUp(self):

        super().setUp()

        self.root_logger = logging.getLogger()
        self.root_level = self.root_logger.level
        self.root_logger.setLevel(logging.INFO)
        self.modules = patch.dict(ibm_i_commands.__dict__, {'noisy': SimpleNamespace(a=noisy_script('AAA'), b=noisy_script('BBB'))})
        self.modules.start()


    def tearDown(self):

        self.modules.stop()
        self.root_logger.setLevel(self.root_level)
        super().tearDown()


    def run_script(self, name: str, results: dict) -> None:

        stage = self.mf.get_stages_by_name('START')[0]
        action = da.Deploy_Action(cmd=f"noisy.{name}", environment=da.Command_Type.SCRIPT, processing_step='step', stage='START')
        action.id = 1
        results[name] = IBM_i_commands.run_script_cmd(IBM_i_commands(self.mf), stage, f"noisy.{name}", action)


    def test_step_log_contains_only_its_own_output(self):

        results = {}
        threads = [threading.Thread(target=self.run_script, args=(name, results)) for name in ['a', 'b']]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for name, own, other in [('a', 'AAA', 'BBB'), ('b', 'BBB', 'AAA')]:
            self.assertEqual(results[name].stdout.count(f"{own} print"), 1000)
            self.assertEqual(results[name].stdout.count(f"{own} log"), 1000)
            self.assertNotIn(other, results[name].stdout)


    def test_streams_and_log_level_are_restored(self):

        stdout, level = sys.stdout, self.root_logger.level
        handlers = len(self.root_logger.handlers)

        self.test_step_log_contains_only_its_own_output()

        self.assertIs(sys.stdout, stdout)
        self.assertEqual(self.root_logger.level, level)
        self.assertEqual(len(self.root_logger.handlers), handlers)
        print('still works')


    def test_other_threads_are_not_captured(self):

        def web_request():
            for _ in range(200):
                logging.info('REQUEST')

        results = {}
        other = threading.Thread(target=web_request)
        other.start()
        self.run_script('a', results)
        other.join()

        self.assertNotIn('REQUEST', results['a'].stdout)
