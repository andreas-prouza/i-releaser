"""How stages follow each other: claims of parallel runs, stages without steps"""
import os, shutil, tempfile, threading, unittest
from types import SimpleNamespace
from unittest.mock import patch

from etc import constants
# Before meta_file (circular import)
from modules import deploy_version
from modules import hooks, meta_file, workflow
from modules.db import app_sqlite, meta_file_data, stage_data
from modules.meta_file_status import Meta_file_status
from modules.stage_status import Status as Stage_Status


WORKFLOW = {
    'name': 'flow_wf',
    'default_project': 'flow',
    'hooks': {'stage_finished': ['flow_hook.call'], 'deployment_finished': ['flow_hook.call']},
    'step_action': [{'processing_step': 'ok', 'environment': 'PASE', 'execute': 'echo ok', 'check_error': True}],
    'stages': [
        {'name': 'START', 'processing_steps': ['ok'], 'next_stages': ['A', 'B']},
        {'name': 'A', 'processing_steps': ['ok'], 'next_stages': ['MERGE']},
        {'name': 'B', 'processing_steps': ['ok'], 'next_stages': ['MERGE']},
        {'name': 'MERGE', 'after_stages_finished': ['A', 'B'], 'next_stages': ['END']},
        {'name': 'END'},
    ],
}



# Stages which wait for parallel stages (docs/bugfixes/merging-stage-ready-too-early.md)
WAIT_WORKFLOW = {
    'name': 'wait_wf',
    'default_project': 'wait',
    'step_action': [{'processing_step': 'ok', 'environment': 'PASE', 'execute': 'echo ok', 'check_error': True}],
    'stages': [
        {'name': 'START', 'processing_steps': ['ok'], 'next_stages': ['A', 'B']},
        {'name': 'A', 'processing_steps': ['ok'], 'next_stages': ['JOIN', 'PART']},
        {'name': 'B', 'processing_steps': ['ok'], 'next_stages': ['JOIN', 'PART']},
        # Runs by itself when A and B are finished
        {'name': 'JOIN', 'processing_steps': ['ok'], 'after_stages_finished': ['A', 'B'], 'run_immediate': True, 'next_stages': ['END']},
        # Reached from A and B, but only waits for A
        {'name': 'PART', 'processing_steps': ['ok'], 'after_stages_finished': ['A'], 'next_stages': ['END']},
        {'name': 'END'},
    ],
}

RESET_WORKFLOW = {
    'name': 'reset_wf',
    'default_project': 'reset',
    'step_action': [{'processing_step': 'ok', 'environment': 'PASE', 'execute': 'echo ok', 'check_error': True}],
    'stages': [
        {'name': 'START', 'processing_steps': ['ok'], 'next_stages': ['A', 'B']},
        {'name': 'A', 'processing_steps': ['ok'], 'next_stages': ['MERGE']},
        {'name': 'B', 'processing_steps': ['ok'], 'next_stages': ['MERGE']},
        {'name': 'MERGE', 'processing_steps': ['ok'], 'after_stages_finished': ['A', 'B'], 'next_stages': ['END']},
        {'name': 'END'},
    ],
}



class Stage_Flow_Setup:
    """A deployment of `workflow_dict` in a temporary database"""

    workflow_dict = WORKFLOW


    def setUp(self):

        self.tmp_dir = tempfile.mkdtemp()
        self.db_file = os.path.join(self.tmp_dir, 'app.sqlite')

        self.db_defaults = app_sqlite.get_db_connection.__defaults__
        app_sqlite.get_db_connection.__defaults__ = (self.db_file,)
        app_sqlite.create_tables(self.db_file)

        self.events = []

        def resolve(execute):
            return lambda event, meta_file, stage: self.events.append((event, stage.name if stage else None))

        self.patches = [
            patch.object(constants, 'C_META_DIR', os.path.join(self.tmp_dir, 'meta', '{project}', '{create_date}', '{deploy_version}')),
            patch.object(workflow.Workflow, 'get_workflow_by_name', return_value=workflow.Workflow(dict=self.workflow_dict)),
            patch.object(workflow.Workflow, 'get_default_step_mapping', return_value=[]),
            patch.object(hooks, 'resolve', side_effect=resolve),
        ]
        for p in self.patches:
            p.start()

        self.mf = meta_file_data.create_new_meta_file(self.workflow_dict['name'])
        self.mf.set_status(Meta_file_status.READY)


    def tearDown(self):

        for p in reversed(self.patches):
            p.stop()

        app_sqlite.get_db_connection.__defaults__ = self.db_defaults
        shutil.rmtree(self.tmp_dir)


    def reload(self) -> meta_file.Meta_File:
        return meta_file_data.get_meta_file_by_id(self.mf.id)


    def stage(self, name: str):
        return self.reload().get_stages_by_name(name)[0]


    def run_stage(self, name: str) -> None:
        mf = self.reload()
        mf.run_current_stage(mf.get_stages_by_name(name)[0].id)


    def waiting_for(self, name: str) -> list:
        mf = self.reload()
        stages = mf.get_all_data_as_dict()['general']
        return {s['name']: s['waiting_for'] for s in stages['open_stages'] + stages['processed_stages']}[name]



class TestStageFlow(Stage_Flow_Setup, unittest.TestCase):


    def test_stage_without_steps_waits_for_its_stages(self):

        self.run_stage('START')
        self.run_stage('A')

        # Not ready before B is finished too
        self.assertEqual(self.stage('MERGE').status, Stage_Status.NEW)
        self.assertEqual(self.waiting_for('MERGE'), ['B'])
        self.assertEqual(self.reload().status, Meta_file_status.READY)


    def test_stages_without_steps_finish_the_deployment(self):

        self.run_stage('START')
        self.run_stage('A')
        self.run_stage('B')

        self.assertEqual(self.stage('MERGE').status, Stage_Status.FINISHED)
        self.assertEqual(self.stage('END').status, Stage_Status.FINISHED)
        self.assertEqual(self.reload().status, Meta_file_status.FINISHED)


    def test_hooks_are_called_once(self):

        self.run_stage('START')
        self.run_stage('A')
        self.run_stage('B')

        self.assertEqual(sorted(self.events, key=str), sorted([('stage_finished', name) for name in ['START', 'A', 'B', 'MERGE', 'END']] + [('deployment_finished', None)], key=str))


    def test_stage_is_activated_once(self):

        self.run_stage('START')

        merge_id = self.stage('MERGE').id
        results = []

        threads = [threading.Thread(target=lambda: results.append(stage_data.activate_stage(merge_id))) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(results.count(True), 1)
        self.assertEqual(self.stage('MERGE').status, Stage_Status.READY)


    def test_stage_is_claimed_once(self):

        stage_id = self.stage('START').id
        results = []

        threads = [threading.Thread(target=lambda: results.append(stage_data.claim_stage(stage_id, exclusive=True))) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(results.count(True), 1)


    def test_activated_stage_is_not_set_back(self):

        self.run_stage('START')

        merge_id = self.stage('MERGE').id
        self.assertTrue(stage_data.activate_stage(merge_id))

        mf = self.reload()
        mf.get_stages_by_name('MERGE')[0].set_status(Stage_Status.FINISHED)

        self.assertFalse(stage_data.activate_stage(merge_id))
        self.assertEqual(self.stage('MERGE').status, Stage_Status.FINISHED)


    def test_exclusive_claim_with_a_running_stage(self):

        self.run_stage('START')

        a, b = self.stage('A').id, self.stage('B').id

        self.assertTrue(stage_data.claim_stage(a, exclusive=True))
        self.assertFalse(stage_data.claim_stage(b, exclusive=True))
        self.assertTrue(stage_data.claim_stage(b, exclusive=False))


    def test_deployment_is_finished_once(self):

        results = []

        threads = [threading.Thread(target=lambda: results.append(meta_file_data.claim_finished(self.mf.id))) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(results.count(True), 1)


    def test_copy_only_writes_what_it_changed(self):

        self.run_stage('START')

        first, second = self.reload(), self.reload()

        first.get_stages_by_name('A')[0].set_status(Stage_Status.IN_PROCESS)

        second.get_stages_by_name('B')[0].status = Stage_Status.IN_PROCESS
        second.save()

        self.assertEqual(self.stage('A').status, Stage_Status.IN_PROCESS)
        self.assertEqual(self.stage('B').status, Stage_Status.IN_PROCESS)



class TestWaitingStages(Stage_Flow_Setup, unittest.TestCase):

    workflow_dict = WAIT_WORKFLOW


    def test_waits_until_all_its_stages_are_finished(self):

        self.run_stage('START')
        self.run_stage('A')

        self.assertEqual(self.stage('JOIN').status, Stage_Status.NEW)
        self.assertEqual(self.waiting_for('JOIN'), ['B'])
        self.assertEqual(self.reload().status, Meta_file_status.READY)

        with self.assertRaises((meta_file.StageNotReadyException, meta_file.StageNotRunnableException)):
            self.run_stage('JOIN')

        self.assertEqual(self.stage('JOIN').status, Stage_Status.NEW)


    def test_runs_immediately_when_the_last_stage_is_finished(self):

        self.run_stage('START')
        self.run_stage('A')
        self.run_stage('B')

        self.assertEqual(self.stage('JOIN').status, Stage_Status.FINISHED)
        self.assertEqual(self.waiting_for('JOIN'), [])


    def test_waits_only_for_the_listed_stages(self):

        self.run_stage('START')

        # PART is reached from B, but waits for A
        self.run_stage('B')
        self.assertEqual(self.stage('PART').status, Stage_Status.NEW)
        self.assertEqual(self.waiting_for('PART'), ['A'])

        self.run_stage('A')
        self.assertEqual(self.stage('PART').status, Stage_Status.READY)
        self.assertEqual(self.waiting_for('PART'), [])


    def test_listed_stage_finished_first(self):

        self.run_stage('START')
        self.run_stage('A')

        # PART only waits for A, JOIN for A and B
        self.assertEqual(self.stage('PART').status, Stage_Status.READY)
        self.assertEqual(self.stage('JOIN').status, Stage_Status.NEW)


    def test_activation_checks_the_stages_it_waits_for(self):

        self.run_stage('START')
        join = self.stage('JOIN').id

        self.assertFalse(stage_data.activate_stage(join, wait_for=['A', 'B']))

        self.reload().get_stages_by_name('A')[0].set_status(Stage_Status.FINISHED)
        self.assertFalse(stage_data.activate_stage(join, wait_for=['A', 'B']))
        self.assertEqual(self.stage('JOIN').status, Stage_Status.NEW)

        self.reload().get_stages_by_name('B')[0].set_status(Stage_Status.FINISHED)
        self.assertTrue(stage_data.activate_stage(join, wait_for=['A', 'B']))
        self.assertEqual(self.stage('JOIN').status, Stage_Status.READY)


    def test_parallel_branches_activate_once(self):

        self.run_stage('START')
        join = self.stage('JOIN').id

        mf = self.reload()
        mf.get_stages_by_name('A')[0].set_status(Stage_Status.FINISHED)
        mf.get_stages_by_name('B')[0].set_status(Stage_Status.FINISHED)

        results = []
        threads = [threading.Thread(target=lambda: results.append(stage_data.activate_stage(join, wait_for=['A', 'B']))) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(results.count(True), 1)
        self.assertEqual(self.stage('JOIN').status, Stage_Status.READY)



class TestResetOfAWaitedStage(Stage_Flow_Setup, unittest.TestCase):

    workflow_dict = RESET_WORKFLOW


    def test_reset_sets_the_waiting_stage_back(self):

        self.run_stage('START')
        self.run_stage('A')
        self.run_stage('B')
        self.assertEqual(self.stage('MERGE').status, Stage_Status.READY)

        # B is the last finished stage. A, which is finished, leads to MERGE as well, but MERGE waits for B.
        mf = self.reload()
        mf.reset_last_finished_stage(mf.get_stages_by_name('B')[0].id)

        self.assertEqual(self.stage('B').status, Stage_Status.READY)
        self.assertEqual(self.stage('MERGE').status, Stage_Status.NEW)
        self.assertEqual(self.waiting_for('MERGE'), ['B'])

        # Run again: MERGE becomes ready again
        self.run_stage('B')
        self.assertEqual(self.stage('MERGE').status, Stage_Status.READY)
