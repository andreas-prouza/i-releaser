"""How stages follow each other: claims of parallel runs, stages without steps"""
import threading, unittest
from unittest.mock import patch

import db_tools
# Before meta_file (circular import)
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



def finish(stage) -> None:
    """A run of the stage, as transitions allow it (modules/state.py)"""
    assert stage.set_status(Stage_Status.IN_PROCESS) and stage.set_status(Stage_Status.FINISHED)



class Stage_Flow_Setup:
    """A deployment of `workflow_dict` in a temporary database"""

    workflow_dict = WORKFLOW


    def setUp(self):

        db_tools.use_temp_db(self)

        self.events = []

        def resolve(execute):
            return lambda event, meta_file, stage: self.events.append((event, stage.name if stage else None))

        self.patches = [
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
        finish(mf.get_stages_by_name('MERGE')[0])

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

        # The status is only changed by a transition, a save never writes it (docs/features/core-redesign.md, step 1)
        second.get_stages_by_name('B')[0].lib_mapping = {'devlib': 'prodlib'}
        second.get_stages_by_name('A')[0].status = Stage_Status.READY
        second.save()

        self.assertEqual(self.stage('A').status, Stage_Status.IN_PROCESS)
        self.assertEqual(self.stage('B').lib_mapping, {'devlib': 'prodlib'})



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

        finish(self.reload().get_stages_by_name('A')[0])
        self.assertFalse(stage_data.activate_stage(join, wait_for=['A', 'B']))
        self.assertEqual(self.stage('JOIN').status, Stage_Status.NEW)

        finish(self.reload().get_stages_by_name('B')[0])
        self.assertTrue(stage_data.activate_stage(join, wait_for=['A', 'B']))
        self.assertEqual(self.stage('JOIN').status, Stage_Status.READY)


    def test_parallel_branches_activate_once(self):

        self.run_stage('START')
        join = self.stage('JOIN').id

        mf = self.reload()
        finish(mf.get_stages_by_name('A')[0])
        finish(mf.get_stages_by_name('B')[0])

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



class TestTransitions(Stage_Flow_Setup, unittest.TestCase):
    """docs/features/core-redesign.md, step 1: a status is only changed by an allowed transition"""


    def test_change_which_is_not_allowed_is_refused(self):

        stage = self.reload().get_stages_by_name('START')[0]

        # ready -> finished without a run
        self.assertFalse(stage.set_status(Stage_Status.FINISHED))
        self.assertEqual(stage.status, Stage_Status.READY)
        self.assertEqual(self.stage('START').status, Stage_Status.READY)


    def test_aborted_run_does_not_finish_the_stage(self):
        """docs/bugfixes/job-abort-leaves-process-running.md: the service has set the stage to failed meanwhile"""

        mf = self.reload()
        start = mf.get_stages_by_name('START')[0]
        mf.claim_stage(start.id)

        # The processing service aborts the run
        self.reload().get_stages_by_name('START')[0].set_status(Stage_Status.FAILED)

        # The process of the run goes on with its outdated copy
        mf.check_stage_finish(start)

        self.assertEqual(self.stage('START').status, Stage_Status.FAILED)
        self.assertEqual(self.stage('A').status, Stage_Status.NEW)
        self.assertNotIn(('stage_finished', 'START'), self.events)


    def test_save_of_an_old_copy_does_not_change_the_status(self):

        old = self.reload()
        self.run_stage('START')

        old.custom_data = {'ticket': 'ABC-1'}
        old.save()

        self.assertEqual(self.stage('START').status, Stage_Status.FINISHED)
        self.assertEqual(self.reload().status, Meta_file_status.READY)


    def test_finished_deployment_does_not_change(self):

        self.assertTrue(meta_file_data.claim_finished(self.mf.id))

        changed, current = meta_file_data.transition(self.mf.id, Meta_file_status.IN_PROCESS)

        self.assertFalse(changed)
        self.assertEqual(current, Meta_file_status.FINISHED)


    def test_edit_of_custom_data_keeps_a_newer_status(self):
        """docs/bugfixes/lost-updates-on-save.md, item 1"""

        with patch.object(workflow.Workflow, 'get_workflow_by_name', return_value=workflow.Workflow(dict={**self.workflow_dict, 'editable_fields': ['$.ticket']})):
            request_copy = self.reload()

        # A stage starts meanwhile
        self.reload().set_status(Meta_file_status.IN_PROCESS)

        request_copy.workflow.editable_fields = ['$.ticket']
        request_copy.update_custom_data({'$.ticket': 'ABC-1'})

        loaded = self.reload()
        self.assertEqual(loaded.status, Meta_file_status.IN_PROCESS)
        self.assertEqual(loaded.custom_data, {'ticket': 'ABC-1'})


    def test_failed_commit_is_written_completely_by_the_next_save(self):
        """docs/bugfixes/lost-updates-on-save.md, item 2"""

        mf = self.reload()
        mf.get_stages_by_name('A')[0].lib_mapping = {'devlib': 'prodlib'}

        with patch.object(meta_file_data, '_save_run_history', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                mf.save()

        self.assertEqual(self.stage('A').lib_mapping, {})

        mf.save()
        self.assertEqual(self.stage('A').lib_mapping, {'devlib': 'prodlib'})


    def test_row_without_id_is_not_updated(self):

        from modules.db import app_sqlite as db
        with db.get_db_connection() as conn:
            with self.assertRaises(ValueError):
                db.update_changes(conn.cursor(), 'stages', None, {'lib_mapping': '{}'}, None)



class TestLoading(Stage_Flow_Setup, unittest.TestCase):
    """docs/features/core-redesign.md, step 2: a deployment is loaded with a fixed number of queries"""


    def add_objects(self, count: int) -> None:

        from modules import deploy_action as da, deploy_object as do
        from modules.db import actions_data, deploy_object_data

        objects = [do.Deploy_Object(level=1, lib='devlib', prod_lib='prodlib', name=f"obj{i}", type='pgm', attribute='rpgle') for i in range(count)]
        deploy_object_data.replace_deploy_objects(self.mf.id, objects)

        for obj in objects:
            for step in ['save', 'restore']:
                action = da.Deploy_Action(cmd=f"echo {step}", processing_step=step, stage='START', environment=da.Command_Type.PASE)
                actions_data.add_action(action, deploy_object_id=obj.id)
                sub = da.Deploy_Action(cmd='echo sub', processing_step=step, stage='START', environment=da.Command_Type.PASE)
                actions_data.add_action(sub, action_id=action.id)


    def count_queries(self, load) -> tuple[int, int]:
        """Connections and statements (without PRAGMA) of `load`"""

        connections, statements = [], []
        original = app_sqlite.get_db_connection

        def counting(*args, **kwargs):
            conn = original(*args, **kwargs)
            connections.append(conn)
            conn.set_trace_callback(lambda sql: None if sql.lstrip().upper().startswith('PRAGMA') else statements.append(sql))
            return conn

        with patch.object(app_sqlite, 'get_db_connection', side_effect=counting):
            load()

        return len(connections), len(statements)


    def test_load_with_200_objects(self):

        self.add_objects(200)
        self.run_stage('START')

        connections, statements = self.count_queries(self.reload)
        loaded = self.reload()

        self.assertEqual(len(loaded.deploy_objects), 200)
        self.assertEqual({len(o.actions) for o in loaded.deploy_objects}, {2})
        self.assertEqual({len(a.sub_actions) for o in loaded.deploy_objects for a in o.actions}, {1})
        self.assertEqual(len(loaded.get_stages_by_name('START')[0].actions[0].run_history), 1)

        self.assertLessEqual(statements, 10)
        self.assertLessEqual(connections, 2)


    def test_same_result_as_the_step_by_step_loading(self):

        from modules.db import actions_data

        self.add_objects(3)
        self.run_stage('START')

        loaded = self.reload()
        for stage in loaded.stages:
            self.assertEqual([a.get_dict() for a in stage.actions], [a.get_dict() for a in actions_data.get_actions(stage_id=stage.id)])
        for obj in loaded.deploy_objects:
            self.assertEqual([a.get_dict() for a in obj.actions], [a.get_dict() for a in actions_data.get_actions(deploy_object_id=obj.id)])



IMMEDIATE_WORKFLOW = {
    'name': 'immediate_wf',
    'default_project': 'immediate',
    'step_action': [{'processing_step': 'ok', 'environment': 'PASE', 'execute': 'echo ok', 'check_error': True},
                    {'processing_step': 'fail', 'environment': 'PASE', 'execute': 'exit 1', 'check_error': True}],
    'stages': [
        {'name': 'START', 'processing_steps': ['ok'], 'next_stages': ['NEXT']},
        {'name': 'NEXT', 'processing_steps': ['fail'], 'next_stages': ['END'], 'run_immediate': True},
        {'name': 'END'},
    ],
}



class TestRunImmediate(Stage_Flow_Setup, unittest.TestCase):
    """docs/features/core-redesign.md, step 3: stages with run_immediate run after the run, not inside it"""

    workflow_dict = IMMEDIATE_WORKFLOW


    def test_failing_next_stage_does_not_fail_the_run(self):

        # Doesn't raise: the error belongs to NEXT
        self.run_stage('START')

        self.assertEqual(self.stage('START').status, Stage_Status.FINISHED)
        self.assertEqual(self.stage('NEXT').status, Stage_Status.FAILED)
        self.assertEqual(self.reload().status, Meta_file_status.FAILED)
