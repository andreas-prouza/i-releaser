import unittest, sys, os, logging, tempfile, shutil
from types import SimpleNamespace
from unittest.mock import patch

# The repository root, so `etc` and `modules` are found
sys.path.insert(0, os.path.realpath(f"{os.path.dirname(__file__)}/.."))

from etc import constants
# Before meta_file (circular import)
from modules import deploy_version
from modules import meta_file, workflow, ibm_i_commands
from modules.stage_status import Status as Stage_Status
from modules.meta_file_status import Meta_file_status
from modules.db import app_sqlite, meta_file_data, processing_job_data



LINEAR_WORKFLOW = {
    'name': 'reset_linear_wf',
    'default_project': 'reset_linear',
    'step_action': [
        {'processing_step': 'echo', 'environment': 'PASE', 'execute': 'echo ok', 'check_error': True},
        {'processing_step': 'maybe_fail', 'environment': 'SCRIPT', 'execute': 'reset_script.maybe_fail', 'check_error': True},
    ],
    'stages': [
        {'name': 'START', 'processing_steps': ['echo'], 'next_stages': ['BUILD']},
        {'name': 'BUILD', 'processing_steps': ['echo', 'maybe_fail'], 'next_stages': ['END']},
        {'name': 'END', 'processing_steps': ['echo']},
    ],
}

PARALLEL_WORKFLOW = {
    'name': 'reset_parallel_wf',
    'default_project': 'reset_parallel',
    'step_action': [
        {'processing_step': 'echo', 'environment': 'PASE', 'execute': 'echo ok', 'check_error': True},
    ],
    'stages': [
        {'name': 'START', 'processing_steps': ['echo'], 'next_stages': ['A', 'B']},
        {'name': 'A', 'processing_steps': ['echo'], 'next_stages': ['C']},
        {'name': 'B', 'processing_steps': ['echo'], 'next_stages': ['C']},
        {'name': 'C', 'processing_steps': ['echo'], 'next_stages': ['END']},
        {'name': 'END'},
    ],
}

WORKFLOWS = {wf['name']: wf for wf in [LINEAR_WORKFLOW, PARALLEL_WORKFLOW]}



class Script:
    fail = False

    @staticmethod
    def maybe_fail(meta_file, stage_obj, action) -> None:
        if Script.fail:
            raise Exception('step failed')



class TestResetLastFinishedStage(unittest.TestCase):


    def setUp(self):

        self.tmp_dir = tempfile.mkdtemp()
        self.db_file = os.path.join(self.tmp_dir, 'app.sqlite')

        # All modules use the default parameter of get_db_connection
        self.db_defaults = app_sqlite.get_db_connection.__defaults__
        app_sqlite.get_db_connection.__defaults__ = (self.db_file,)
        app_sqlite.create_tables(self.db_file)

        Script.fail = False

        self.patches = [
            patch.object(constants, 'C_META_DIR', os.path.join(self.tmp_dir, 'meta', '{project}', '{create_date}', '{deploy_version}')),
            patch.object(workflow.Workflow, 'get_workflow_by_name', side_effect=lambda name: workflow.Workflow(dict=WORKFLOWS[name])),
            patch.object(workflow.Workflow, 'get_default_step_mapping', return_value=[]),
            patch.dict(ibm_i_commands.__dict__, {'reset_script': SimpleNamespace(maybe_fail=Script.maybe_fail)}),
        ]
        for p in self.patches:
            p.start()

        self.root_logger = logging.getLogger()
        self.root_level = self.root_logger.level
        self.root_logger.setLevel(logging.CRITICAL)


    def tearDown(self):

        self.root_logger.setLevel(self.root_level)

        for p in reversed(self.patches):
            p.stop()

        app_sqlite.get_db_connection.__defaults__ = self.db_defaults
        shutil.rmtree(self.tmp_dir, ignore_errors=True)



    def create_meta_file(self, wf: dict=LINEAR_WORKFLOW) -> meta_file.Meta_File:
        mf = meta_file_data.create_new_meta_file(workflow_name=wf['name'])
        mf.set_status(Meta_file_status.READY)
        return self.reload(mf)


    def reload(self, mf: meta_file.Meta_File) -> meta_file.Meta_File:
        return meta_file_data.get_meta_file_by_id(mf.id)


    def stage(self, mf: meta_file.Meta_File, name: str):
        return mf.get_stages_by_name(name)[0]


    def run_stage(self, mf: meta_file.Meta_File, name: str, continue_run=True) -> meta_file.Meta_File:
        """Like the web app: always works on a freshly loaded deployment"""
        mf = self.reload(mf)
        try:
            mf.run_current_stage(self.stage(mf, name).id, continue_run=continue_run)
        except Exception:
            pass
        return self.reload(mf)


    def reset(self, mf: meta_file.Meta_File, name: str) -> meta_file.Meta_File:
        mf = self.reload(mf)
        mf.reset_last_finished_stage(self.stage(mf, name).id)
        return self.reload(mf)


    def statuses(self, mf: meta_file.Meta_File) -> dict:
        return {stage.name: stage.status for stage in mf.stages}



    def test_reset_opens_stage_again_and_closes_next_stages(self):

        mf = self.run_stage(self.create_meta_file(), 'START')
        self.assertEqual(self.statuses(mf), {'START': Stage_Status.FINISHED, 'BUILD': Stage_Status.READY, 'END': Stage_Status.NEW})
        self.assertEqual(mf.get_last_finished_stage().name, 'START')

        mf = self.reset(mf, 'START')

        self.assertEqual(self.statuses(mf), {'START': Stage_Status.READY, 'BUILD': Stage_Status.NEW, 'END': Stage_Status.NEW})
        self.assertEqual(self.stage(mf, 'START').next_stage_ids, [])
        self.assertEqual(mf.status, Meta_file_status.READY)
        self.assertIsNone(mf.get_last_finished_stage())



    def test_stage_can_be_run_again_after_reset(self):

        mf = self.run_stage(self.create_meta_file(), 'START')
        mf = self.reset(mf, 'START')

        # Steps keep their status: continue just finishes the stage again
        mf = self.run_stage(mf, 'START')
        start = self.stage(mf, 'START')
        self.assertEqual(start.status, Stage_Status.FINISHED)
        self.assertEqual(len(start.actions[0].run_history), 1)

        mf = self.reset(mf, 'START')
        mf = self.run_stage(mf, 'START', continue_run=False)
        start = self.stage(mf, 'START')
        self.assertEqual(start.status, Stage_Status.FINISHED)
        self.assertEqual(len(start.actions[0].run_history), 2)

        build = self.stage(mf, 'BUILD')
        self.assertEqual(build.status, Stage_Status.READY)
        self.assertEqual(start.next_stage_ids, [build.id])



    def test_only_last_finished_stage(self):

        mf = self.run_stage(self.create_meta_file(), 'START')
        mf = self.run_stage(mf, 'BUILD')
        self.assertEqual(mf.get_last_finished_stage().name, 'BUILD')

        with self.assertRaisesRegex(Exception, "not the last finished stage"):
            mf.reset_last_finished_stage(self.stage(mf, 'START').id)
        self.assertEqual(self.statuses(self.reload(mf)), {'START': Stage_Status.FINISHED, 'BUILD': Stage_Status.FINISHED, 'END': Stage_Status.READY})

        # Step by step back
        mf = self.reset(mf, 'BUILD')
        self.assertEqual(self.statuses(mf), {'START': Stage_Status.FINISHED, 'BUILD': Stage_Status.READY, 'END': Stage_Status.NEW})

        mf = self.reset(mf, 'START')
        self.assertEqual(self.statuses(mf), {'START': Stage_Status.READY, 'BUILD': Stage_Status.NEW, 'END': Stage_Status.NEW})



    def test_reset_after_next_stage_failed(self):

        mf = self.run_stage(self.create_meta_file(), 'START')
        Script.fail = True
        mf = self.run_stage(mf, 'BUILD')
        self.assertEqual(self.stage(mf, 'BUILD').status, Stage_Status.FAILED)
        self.assertEqual(mf.status, Meta_file_status.FAILED)

        mf = self.reset(mf, 'START')

        self.assertEqual(self.statuses(mf), {'START': Stage_Status.READY, 'BUILD': Stage_Status.NEW, 'END': Stage_Status.NEW})
        self.assertEqual(mf.status, Meta_file_status.READY)



    def test_parallel_next_stage_stays_open_if_reached_from_other_finished_stage(self):

        mf = self.create_meta_file(PARALLEL_WORKFLOW)
        for name in ['START', 'A', 'B']:
            mf = self.run_stage(mf, name)
        self.assertEqual(self.stage(mf, 'C').status, Stage_Status.READY)
        self.assertEqual(mf.get_last_finished_stage().name, 'B')

        # C is still reached from A
        mf = self.reset(mf, 'B')
        self.assertEqual(self.statuses(mf), {'START': Stage_Status.FINISHED, 'A': Stage_Status.FINISHED, 'B': Stage_Status.READY, 'C': Stage_Status.READY, 'END': Stage_Status.NEW})

        mf = self.reset(mf, 'A')
        self.assertEqual(self.statuses(mf), {'START': Stage_Status.FINISHED, 'A': Stage_Status.READY, 'B': Stage_Status.READY, 'C': Stage_Status.NEW, 'END': Stage_Status.NEW})



    def test_not_allowed_while_stage_in_process(self):

        mf = self.run_stage(self.create_meta_file(), 'START')
        self.stage(mf, 'BUILD').set_status(Stage_Status.IN_PROCESS)
        mf = self.reload(mf)

        with self.assertRaisesRegex(Exception, "still in process"):
            mf.reset_last_finished_stage(self.stage(mf, 'START').id)
        self.assertEqual(self.stage(self.reload(mf), 'START').status, Stage_Status.FINISHED)



    def test_not_allowed_while_deployment_in_process(self):

        mf = self.run_stage(self.create_meta_file(), 'START')
        mf.set_status(Meta_file_status.IN_PROCESS)

        with self.assertRaisesRegex(Exception, "in status 'in process'"):
            self.reload(mf).check_reset_last_finished_stage()



    def test_not_allowed_with_active_job(self):

        mf = self.run_stage(self.create_meta_file(), 'START')
        job = processing_job_data.create_job(meta_file_id=mf.id, stage_id=self.stage(mf, 'BUILD').id)

        with self.assertRaisesRegex(Exception, f"'BUILD' is queued in the processing service \\(job {job.id}\\)"):
            self.reload(mf).check_reset_last_finished_stage()

        processing_job_data.cancel_job(job.id)
        self.assertEqual(self.reload(mf).check_reset_last_finished_stage().name, 'START')



    def test_not_allowed_when_deployment_finished(self):

        mf = self.create_meta_file()
        for name in ['START', 'BUILD', 'END']:
            mf = self.run_stage(mf, name)
        self.assertEqual(mf.status, Meta_file_status.FINISHED)

        with self.assertRaisesRegex(Exception, "already finished"):
            mf.reset_last_finished_stage(self.stage(mf, 'END').id)



    def test_not_allowed_when_deployment_canceled(self):

        mf = self.run_stage(self.create_meta_file(), 'START')
        mf.cancel_deployment()

        with self.assertRaisesRegex(Exception, "already canceled"):
            self.reload(mf).check_reset_last_finished_stage()



    def test_no_finished_stage(self):

        mf = self.create_meta_file()

        self.assertIsNone(mf.get_last_finished_stage())
        with self.assertRaisesRegex(Exception, "No stage has been finished yet"):
            mf.check_reset_last_finished_stage()



if __name__ == '__main__':
    unittest.main()
