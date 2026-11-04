"""Steps which run at the same time: groups, waiting, failures, limit and what they share"""
import logging, os, shutil, tempfile, threading, time, unittest
from types import SimpleNamespace
from unittest.mock import patch

from etc import constants
# Before meta_file (circular import)
from modules import deploy_version
from modules import current_user, files, ibm_i_commands, meta_file, stage_status, workflow
from modules import deploy_action as da
from modules.cmd_status import Status as Cmd_Status
from modules.db import app_sqlite, meta_file_data
from modules.ibm_i_commands import Command_Exception, IBM_i_commands
from modules.meta_file_status import Meta_file_status


WORKFLOW = {
    'name': 'parallel_wf',
    'default_project': 'parallel',
    'step_action': [{'processing_step': 'first', 'environment': 'PASE', 'execute': 'echo first', 'check_error': True}],
    'stages': [{'name': 'START', 'processing_steps': ['first'], 'next_stages': ['END']}, {'name': 'END'}],
}

GROUP = {'parallel_group': 'group 1', 'parallel': True}



def sub_step(stage_obj, action: da.Deploy_Action, cmd: str, **kwargs) -> da.Deploy_Action:
    return action.sub_actions.add_action(da.Deploy_Action(cmd=cmd, environment=da.Command_Type.PASE, processing_step=action.processing_step, stage=stage_obj.name, **kwargs))



def read_log(log: str) -> str:
    return files.readFile(log.removeprefix('file://'))



class Parallel_Test(unittest.TestCase):


    def setUp(self):

        self.tmp_dir = tempfile.mkdtemp()
        self.db_file = os.path.join(self.tmp_dir, 'app.sqlite')
        self.meet_dir = os.path.join(self.tmp_dir, 'meet')
        os.makedirs(self.meet_dir)

        self.db_defaults = app_sqlite.get_db_connection.__defaults__
        app_sqlite.get_db_connection.__defaults__ = (self.db_file,)
        app_sqlite.create_tables(self.db_file)

        self.scripts = SimpleNamespace()

        self.patches = [
            patch.object(constants, 'C_META_DIR', os.path.join(self.tmp_dir, 'meta', '{project}', '{create_date}', '{deploy_version}')),
            patch.object(workflow.Workflow, 'get_workflow_by_name', return_value=workflow.Workflow(dict=WORKFLOW)),
            patch.object(workflow.Workflow, 'get_default_step_mapping', return_value=[]),
            patch.dict(ibm_i_commands.__dict__, {'test_script': self.scripts}),
        ]
        for p in self.patches:
            p.start()

        self.mf = meta_file_data.create_new_meta_file(WORKFLOW['name'])
        self.mf.set_status(Meta_file_status.READY)
        self.stage = self.mf.get_stages_by_name('START')[0]


    def tearDown(self):

        for p in reversed(self.patches):
            p.stop()

        app_sqlite.get_db_connection.__defaults__ = self.db_defaults
        shutil.rmtree(self.tmp_dir, ignore_errors=True)


    def add_step(self, cmd: str, environment=da.Command_Type.PASE, **kwargs) -> da.Deploy_Action:
        return self.stage.actions.add_action_cmd(cmd=cmd, environment=environment, processing_step='step', stage='START', **kwargs)


    def add_script(self, function, **kwargs) -> da.Deploy_Action:
        setattr(self.scripts, function.__name__, function)
        return self.add_step(f"test_script.{function.__name__}", da.Command_Type.SCRIPT, **kwargs)


    def run_stage(self, **kwargs) -> None:
        self.mf.save()
        self.mf.run_current_stage(self.stage.id, **kwargs)


    def path(self, name: str) -> str:
        return os.path.join(self.tmp_dir, name)


    def meet(self, name: str, count: int) -> str:
        """A command which only succeeds, if `count` of these commands run at the same time"""
        return f"touch {self.meet_dir}/{name}; for i in $(seq 200); do [ $(ls {self.meet_dir} | wc -l) -ge {count} ] && exit 0; sleep 0.02; done; exit 1"


    def stored_stage(self):
        return meta_file_data.get_meta_file_by_id(self.mf.id).get_stages_by_name('START')[0]



class TestGroups(Parallel_Test):


    def test_execute_action_returns_while_the_step_is_running(self):

        go = self.path('go')
        status = []

        def start(meta_file, stage_obj, action):
            step = sub_step(stage_obj, action, f"until [ -f {go} ]; do sleep 0.02; done", timeout_seconds=5, **GROUP)
            IBM_i_commands(meta_file).execute_action(stage_obj, step)
            status.append(step.status)
            open(go, 'w').close()

        parent = self.add_script(start)
        self.run_stage()

        self.assertEqual(status, [Cmd_Status.NEW])
        self.assertEqual(parent.sub_actions[0].status, Cmd_Status.FINISHED)


    def test_steps_of_a_group_run_at_the_same_time(self):

        steps = [self.add_step(self.meet(name, 3), **GROUP) for name in 'abc']
        self.run_stage()

        self.assertEqual([step.status for step in steps], [Cmd_Status.FINISHED] * 3)


    def test_sub_steps_and_steps_are_the_same(self):

        def start(meta_file, stage_obj, action):
            cmd = IBM_i_commands(meta_file)
            for name in 'ab':
                cmd.execute_action(stage_obj, sub_step(stage_obj, action, self.meet(name, 2), **GROUP))

        parent = self.add_script(start)
        self.run_stage()

        self.assertEqual([step.status for step in parent.sub_actions], [Cmd_Status.FINISHED] * 2)


    def test_group_ends_with_a_step_without_parallel(self):

        done = self.path('done')

        self.add_step(f"sleep 0.3; touch {done}", **GROUP)
        last = self.add_step(f"test -f {done}")
        self.run_stage()

        self.assertEqual(last.status, Cmd_Status.FINISHED)


    def test_group_ends_with_a_step_of_the_same_group_without_parallel(self):

        done = self.path('done')

        self.add_step(f"sleep 0.3; touch {done}", **GROUP)
        last = self.add_step(f"test -f {done}", parallel_group=GROUP['parallel_group'])
        self.run_stage()

        self.assertEqual(last.status, Cmd_Status.FINISHED)


    def test_group_ends_with_another_group(self):

        done = self.path('done')

        self.add_step(f"sleep 0.3; touch {done}", **GROUP)
        last = self.add_step(f"test -f {done}", parallel_group='group 2', parallel=True)
        self.run_stage()

        self.assertEqual(last.status, Cmd_Status.FINISHED)


    def test_a_group_can_start_again_after_another_group(self):

        done = self.path('done')

        self.add_step(f"sleep 0.3; touch {done}", **GROUP)
        self.add_step(f"test -f {done}; touch {done}.2; sleep 0.3; touch {done}.3", parallel_group='group 2', parallel=True)
        last = self.add_step(f"test -f {done}.3", **GROUP)
        self.run_stage()

        self.assertEqual(last.status, Cmd_Status.FINISHED)


    def test_parallel_without_group_name(self):

        steps = [self.add_step(self.meet(name, 2), parallel=True) for name in 'ab']
        self.run_stage()

        self.assertEqual([step.status for step in steps], [Cmd_Status.FINISHED] * 2)


    def test_group_name_alone_is_not_parallel(self):

        done = self.path('done')

        self.add_step(f"sleep 0.3; touch {done}", parallel_group='group 1')
        last = self.add_step(f"test -f {done}", parallel_group='group 1')
        self.run_stage()

        self.assertEqual(last.status, Cmd_Status.FINISHED)


    @patch.object(constants, 'C_MAX_PARALLEL_STEPS', 2)
    def test_limit_of_a_group(self):

        lock = threading.Lock()
        running = []
        counts = []

        def work(meta_file, stage_obj, action):

            with lock:
                running.append(action)
                counts.append(len(running))

            time.sleep(0.1)

            with lock:
                running.remove(action)

        steps = [self.add_script(work, **GROUP) for _ in range(6)]
        self.run_stage()

        self.assertEqual([step.status for step in steps], [Cmd_Status.FINISHED] * 6)
        self.assertEqual(max(counts), 2)


    def test_outside_of_a_run_the_step_is_finished_when_it_returns(self):

        step = self.add_step('echo ok', **GROUP)
        self.mf.save()

        IBM_i_commands(self.mf).execute_action(self.stage, step)

        self.assertEqual(step.status, Cmd_Status.FINISHED)



class TestScripts(Parallel_Test):


    def test_script_has_ended_after_its_sub_steps(self):

        done = self.path('done')

        def start(meta_file, stage_obj, action):
            IBM_i_commands(meta_file).execute_action(stage_obj, sub_step(stage_obj, action, f"sleep 0.3; touch {done}", **GROUP))

        self.add_script(start)
        last = self.add_step(f"test -f {done}")
        self.run_stage()

        self.assertEqual(last.status, Cmd_Status.FINISHED)


    def test_instances_of_the_commands_share_the_group(self):

        status = []

        def start(meta_file, stage_obj, action):
            for name in 'ab':
                IBM_i_commands(meta_file).execute_action(stage_obj, sub_step(stage_obj, action, self.meet(name, 2), **GROUP))

            IBM_i_commands(meta_file).wait_for_parallel_actions()
            status.extend(step.status for step in action.sub_actions)

        self.add_script(start)
        self.run_stage()

        self.assertEqual(status, [Cmd_Status.FINISHED] * 2)


    def test_sub_steps_do_not_end_the_group_of_the_stage(self):

        def start(meta_file, stage_obj, action):
            IBM_i_commands(meta_file).execute_action(stage_obj, sub_step(stage_obj, action, self.meet('sub_step', 2)))

        parent = self.add_script(start, **GROUP)
        step = self.add_step(self.meet('step', 2), **GROUP)
        self.run_stage()

        self.assertEqual([parent.status, step.status], [Cmd_Status.FINISHED] * 2)


    def test_wait_raises_the_failure(self):

        errors = []

        def start(meta_file, stage_obj, action):

            cmd = IBM_i_commands(meta_file)
            cmd.execute_action(stage_obj, sub_step(stage_obj, action, 'exit 1', **GROUP))

            try:
                cmd.wait_for_parallel_actions()
            except Command_Exception as e:
                errors.append(e)

        parent = self.add_script(start)
        self.run_stage()

        self.assertEqual(len(errors), 1)
        self.assertEqual(parent.status, Cmd_Status.FINISHED)


    def test_next_step_raises_the_failure(self):

        last = []

        def start(meta_file, stage_obj, action):

            cmd = IBM_i_commands(meta_file)
            cmd.execute_action(stage_obj, sub_step(stage_obj, action, 'exit 1', **GROUP))

            last.append(sub_step(stage_obj, action, 'echo last'))
            cmd.execute_action(stage_obj, last[0])

        parent = self.add_script(start)

        with self.assertRaises(Command_Exception):
            self.run_stage()

        self.assertEqual(last[0].status, Cmd_Status.NEW)
        self.assertEqual(parent.status, Cmd_Status.FAILED)


    @patch.object(constants, 'C_MAX_PARALLEL_STEPS', 1)
    def test_failed_script_waits_for_its_sub_steps(self):

        done = self.path('done')
        steps = []

        def start(meta_file, stage_obj, action):

            cmd = IBM_i_commands(meta_file)
            steps.append(sub_step(stage_obj, action, f"sleep 0.3; touch {done}", **GROUP))
            steps.append(sub_step(stage_obj, action, 'echo not started', **GROUP))

            for step in steps:
                cmd.execute_action(stage_obj, step)

            raise Exception('Script failed')

        parent = self.add_script(start)

        with self.assertRaises(Command_Exception):
            self.run_stage()

        self.assertTrue(os.path.exists(done))
        self.assertEqual([step.status for step in steps], [Cmd_Status.FINISHED, Cmd_Status.NEW])
        self.assertIn('Script failed', read_log(parent.run_history[-1].stderr))


    @patch.object(constants, 'C_MAX_PARALLEL_STEPS', 8)
    def test_sub_steps_are_stored_once(self):

        def start(meta_file, stage_obj, action):

            cmd = IBM_i_commands(meta_file)
            for i in range(30):
                cmd.execute_action(stage_obj, sub_step(stage_obj, action, f"echo {i}", **GROUP))

        parent = self.add_script(start)
        self.run_stage()

        stored = self.stored_stage().actions.get_action_by_id(parent.id)

        self.assertEqual(sorted(step.cmd for step in stored.sub_actions), sorted(f"echo {i}" for i in range(30)))
        self.assertEqual({step.status for step in stored.sub_actions}, {Cmd_Status.FINISHED})
        self.assertEqual({len(step.run_history) for step in stored.sub_actions}, {1})


    @patch.object(constants, 'C_MAX_PARALLEL_STEPS', 8)
    def test_saves_of_steps_do_not_overlap(self):

        save_meta_file = meta_file_data.save_meta_file
        lock = threading.Lock()
        running = []
        counts = []

        def counting_save(mf):

            with lock:
                running.append(mf)
                counts.append(len(running))

            time.sleep(0.01)
            save_meta_file(mf)

            with lock:
                running.remove(mf)

        steps = [self.add_step('echo ok', **GROUP) for _ in range(8)]

        with patch.object(meta_file_data, 'save_meta_file', counting_save):
            self.run_stage()

        self.assertEqual({step.status for step in steps}, {Cmd_Status.FINISHED})
        self.assertEqual(max(counts), 1)



class TestFailure(Parallel_Test):


    @patch.object(constants, 'C_MAX_PARALLEL_STEPS', 2)
    def test_running_steps_end_and_no_further_step_starts(self):

        running = self.path('running')
        not_started = self.path('not_started')

        failing = self.add_step(f"({self.meet('failing', 2)}); exit 1", **GROUP)
        slow = self.add_step(f"({self.meet('slow', 2)}) && sleep 0.5 && touch {running}", **GROUP)
        queued = self.add_step(f"touch {not_started}", **GROUP)
        last = self.add_step(f"touch {not_started}")

        with self.assertRaises(Command_Exception):
            self.run_stage()

        self.assertEqual(failing.status, Cmd_Status.FAILED)
        self.assertEqual(slow.status, Cmd_Status.FINISHED)
        self.assertTrue(os.path.exists(running))
        self.assertEqual([queued.status, last.status], [Cmd_Status.NEW] * 2)
        self.assertFalse(os.path.exists(not_started))

        self.assertEqual(self.stage.status, stage_status.Status.FAILED)
        self.assertEqual(self.stored_stage().status, stage_status.Status.FAILED)
        self.assertEqual(self.mf.status, Meta_file_status.FAILED)


    def test_stage_stays_in_process_while_steps_are_running(self):

        failing = self.add_step('exit 1', **GROUP)
        status = []

        def watch(meta_file, stage_obj, action):

            end = time.monotonic() + 5

            while self.stored_stage().actions.get_action_by_id(failing.id).status != Cmd_Status.FAILED and time.monotonic() < end:
                time.sleep(0.01)

            status.append(self.stored_stage().status)

        self.add_script(watch, **GROUP)

        with self.assertRaises(Command_Exception):
            self.run_stage()

        # A failed stage can be run again
        self.assertEqual(status, [stage_status.Status.IN_PROCESS])


    def test_step_without_error_check_does_not_stop_the_stage(self):

        failing = self.add_step('exit 1', check_error=False, **GROUP)
        step = self.add_step('echo ok', **GROUP)
        last = self.add_step('echo last')

        self.run_stage()

        self.assertEqual([failing.status, step.status, last.status], [Cmd_Status.FAILED, Cmd_Status.FINISHED, Cmd_Status.FINISHED])
        self.assertEqual(self.stage.status, stage_status.Status.FINISHED)


    def test_run_again_only_runs_what_has_not_been_finished(self):

        runs = self.path('runs')
        fixed = self.path('fixed')

        self.add_step(f"echo ok >> {runs}", **GROUP)
        self.add_step(f"echo failing >> {runs}; test -f {fixed}", **GROUP)

        with self.assertRaises(Command_Exception):
            self.run_stage()

        open(fixed, 'w').close()
        self.run_stage()

        self.assertEqual(sorted(files.readFile(runs).split()), ['failing', 'failing', 'ok'])
        self.assertEqual(self.stage.status, stage_status.Status.FINISHED)



class TestSharedState(Parallel_Test):


    def setUp(self):

        super().setUp()

        self.root_logger = logging.getLogger()
        self.root_level = self.root_logger.level
        self.root_logger.setLevel(logging.INFO)


    def tearDown(self):

        self.root_logger.setLevel(self.root_level)
        super().tearDown()


    def test_step_runs_with_the_user_of_the_stage(self):

        users = []

        def remember(meta_file, stage_obj, action):
            users.append(current_user.get_user())

        self.add_script(remember, **GROUP)

        current_user.set_user('tester')
        self.addCleanup(current_user.set_user, None)

        self.run_stage()

        self.assertEqual(users, ['TESTER'])


    def test_log_of_a_step_is_in_the_history_of_the_deployment(self):

        def write(meta_file, stage_obj, action):
            logging.info('Log of a parallel step')

        self.add_script(write, **GROUP)
        self.run_stage()

        self.assertIn('Log of a parallel step', read_log(self.mf.run_history[-1].log))


    def test_output_stays_with_its_step(self):

        def one(meta_file, stage_obj, action):
            print('Output of one')
            time.sleep(0.1)

        def two(meta_file, stage_obj, action):
            print('Output of two')
            time.sleep(0.1)

        first = self.add_script(one, **GROUP)
        second = self.add_script(two, **GROUP)
        self.run_stage()

        self.assertIn('Output of one', read_log(first.run_history[-1].stdout))
        self.assertNotIn('Output of two', read_log(first.run_history[-1].stdout))
        self.assertIn('Output of two', read_log(second.run_history[-1].stdout))
        self.assertNotIn('Output of one', read_log(second.run_history[-1].stdout))



class TestDefinition(Parallel_Test):


    def test_attributes_are_stored(self):

        step = self.add_step('echo ok', **GROUP)
        other = self.add_step('echo ok')
        self.mf.save()

        stored = self.stored_stage().actions

        self.assertEqual(stored.get_action_by_id(step.id).parallel_group, 'group 1')
        self.assertTrue(stored.get_action_by_id(step.id).parallel)
        self.assertIsNone(stored.get_action_by_id(other.id).parallel_group)
        self.assertFalse(stored.get_action_by_id(other.id).parallel)


    def test_attributes_of_a_step_action(self):

        definition = {**WORKFLOW, 'step_action': [{**WORKFLOW['step_action'][0], **GROUP}]}

        workflow.Workflow.validate_workflow(definition, 'test.json')
        stage = meta_file.s.Stage.get_stage_from_workflow(workflow.Workflow(dict=definition), 'START')

        self.assertEqual(stage.actions[0].parallel_group, 'group 1')
        self.assertTrue(stage.actions[0].parallel)


    def test_attributes_of_an_object_command(self):

        action = da.Deploy_Action(dict_data={'cmd': 'echo ok', 'processing_step': 'step', **GROUP}, stage='START')

        self.assertEqual(action.parallel_group, 'group 1')
        self.assertTrue(action.parallel)

        self.assertEqual(action.get_dict()['parallel_group'], 'group 1')
        self.assertTrue(action.get_dict()['parallel'])
