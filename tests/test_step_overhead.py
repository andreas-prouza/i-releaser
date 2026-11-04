import unittest, sys, os, logging, sqlite3, tempfile, shutil, threading
from types import SimpleNamespace
from unittest.mock import patch

# The repository root, so `etc` and `modules` are found
sys.path.insert(0, os.path.realpath(f"{os.path.dirname(__file__)}/.."))

from etc import constants
# Before meta_file (circular import)
from modules import deploy_version
from modules import meta_file, workflow, ibm_i_commands, files
from modules import deploy_action as da
from modules.db import app_sqlite, meta_file_data, meta_file_history_data



WORKFLOW = {
    'name': 'overhead_wf',
    'default_project': 'overhead',
    'step_action': [
        {'processing_step': 'plain', 'environment': 'PASE', 'execute': 'echo plain', 'check_error': True},
        {'processing_step': 'placeholder', 'environment': 'PASE', 'execute': 'echo id={meta_file[general][id]}', 'check_error': True},
        {'processing_step': 'script', 'environment': 'SCRIPT', 'execute': 'overhead_script.run_sub_actions', 'check_error': True},
    ],
    'stages': [
        {'name': 'START', 'processing_steps': ['plain', 'placeholder', 'script'], 'next_stages': ['END']},
        {'name': 'END', 'processing_steps': ['plain']},
    ],
}



def run_sub_actions(meta_file: meta_file.Meta_File, stage_obj, action: da.Deploy_Action) -> None:
    """Same pattern as save_objects.init_save: execute sub actions from within a script"""

    cmd = ibm_i_commands.IBM_i_commands(meta_file)
    for i in range(3):
        sub_action = action.sub_actions.add_action(da.Deploy_Action(
            cmd=f"echo sub {i}",
            environment=da.Command_Type.PASE,
            processing_step=action.processing_step,
            stage=stage_obj.name,
        ))
        cmd.execute_action(stage=stage_obj, action=sub_action)



def read_log(log: str) -> str:
    return files.readFile(log.removeprefix('file://'))



class TestStepOverhead(unittest.TestCase):


    def setUp(self):

        self.tmp_dir = tempfile.mkdtemp()
        self.db_file = os.path.join(self.tmp_dir, 'app.sqlite')

        # All modules use the default parameter of get_db_connection
        self.db_defaults = app_sqlite.get_db_connection.__defaults__
        app_sqlite.get_db_connection.__defaults__ = (self.db_file,)
        app_sqlite.create_tables(self.db_file)

        self.patches = [
            patch.object(constants, 'C_META_DIR', os.path.join(self.tmp_dir, 'meta', '{project}', '{create_date}', '{deploy_version}')),
            patch.object(workflow.Workflow, 'get_workflow_by_name', return_value=workflow.Workflow(dict=WORKFLOW)),
            patch.object(workflow.Workflow, 'get_default_step_mapping', return_value=[]),
            patch.dict(ibm_i_commands.__dict__, {'overhead_script': SimpleNamespace(run_sub_actions=run_sub_actions)}),
        ]
        for p in self.patches:
            p.start()

        self.root_logger = logging.getLogger()
        self.root_level = self.root_logger.level
        self.root_logger.setLevel(logging.INFO)
        self.null_handler = logging.NullHandler()
        self.root_logger.addHandler(self.null_handler)
        self.handler_count = len(self.root_logger.handlers)


    def tearDown(self):

        self.root_logger.removeHandler(self.null_handler)
        self.root_logger.setLevel(self.root_level)

        for p in reversed(self.patches):
            p.stop()

        app_sqlite.get_db_connection.__defaults__ = self.db_defaults
        shutil.rmtree(self.tmp_dir, ignore_errors=True)


    def create_meta_file(self) -> meta_file.Meta_File:
        mf = meta_file_data.create_new_meta_file(workflow_name=WORKFLOW['name'])
        mf.set_status(meta_file.Meta_file_status.READY)
        return mf


    def run_start_stage(self, mf: meta_file.Meta_File) -> None:
        mf.run_current_stage(mf.get_stages_by_name('START')[0].id)



    def test_load_adds_no_log_handler(self):

        mf = self.create_meta_file()
        self.assertEqual(len(self.root_logger.handlers), self.handler_count)

        for _ in range(5):
            meta_file_data.get_meta_file_by_id(mf.id)

        self.assertEqual(len(self.root_logger.handlers), self.handler_count)



    def test_history_contains_only_own_thread(self):

        mf = self.create_meta_file()

        self.assertTrue(mf.activate_history())
        self.assertFalse(mf.activate_history())
        self.assertEqual(len(self.root_logger.handlers), self.handler_count + 1)

        logging.info('own thread')
        other_thread = threading.Thread(target=logging.info, args=('other thread',))
        other_thread.start()
        other_thread.join()

        mf.deactivate_history()
        self.assertEqual(len(self.root_logger.handlers), self.handler_count)

        history = mf.run_history[-1]
        self.assertIsNotNone(history.id)
        self.assertTrue(history.log.startswith('file://'))
        self.assertEqual(meta_file_history_data.get_run_history_by_id(history.id).log, read_log(history.log))

        log = read_log(history.log)
        self.assertIn('own thread', log)
        self.assertNotIn('other thread', log)



    def test_run_stage(self):

        mf = self.create_meta_file()
        histories = len(mf.run_history)

        with patch.object(meta_file.Meta_File, 'get_all_data_as_dict', autospec=True, side_effect=meta_file.Meta_File.get_all_data_as_dict) as get_all_data, \
             patch.object(meta_file_data, 'get_meta_dir', wraps=meta_file_data.get_meta_dir) as get_meta_dir:
            self.run_start_stage(mf)

        self.assertEqual(len(self.root_logger.handlers), self.handler_count)

        # Only needed for the placeholder
        self.assertEqual(get_all_data.call_count, 1)
        # Known from the meta file
        get_meta_dir.assert_not_called()

        stage = meta_file_data.get_meta_file_by_id(mf.id).get_stages_by_name('START')[0]
        actions = {a.processing_step: a for a in stage.actions}

        self.assertEqual(read_log(actions['plain'].run_history[-1].stdout), 'plain\n')
        self.assertEqual(read_log(actions['placeholder'].run_history[-1].stdout), f'id={mf.id}\n')

        sub_actions = actions['script'].sub_actions
        self.assertEqual(len(sub_actions), 3)
        for i, sub_action in enumerate(sorted(sub_actions, key=lambda a: a.sequence)):
            self.assertIsNotNone(sub_action.id)
            self.assertEqual(sub_action.status, da.Cmd_Status.FINISHED)
            self.assertEqual(read_log(sub_action.run_history[-1].stdout), f'sub {i}\n')

        # One new history for the run, which contains its logs
        self.assertEqual(len(mf.run_history), histories + 1)
        self.assertIn("Run stage START", read_log(mf.run_history[-1].log))
        self.assertIn("took", read_log(mf.run_history[-1].log))



    def test_history_deactivated_on_error(self):

        mf = self.create_meta_file()

        with patch.object(meta_file.Meta_File, '_run_current_stage', side_effect=Exception('failed')):
            self.assertRaises(Exception, self.run_start_stage, mf)

        self.assertEqual(len(self.root_logger.handlers), self.handler_count)
        self.assertIsNone(mf._history_handler)



    def test_save_keeps_history_logs(self):

        mf = self.create_meta_file()
        self.run_start_stage(mf)
        log = read_log(mf.run_history[-1].log)

        loaded = meta_file_data.get_meta_file_by_id(mf.id)
        loaded.save()

        self.assertEqual(read_log(loaded.run_history[-1].log), log)



    def test_create_tables(self):

        with sqlite3.connect(self.db_file) as conn:
            indexes = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")]
        for table, column in app_sqlite.INDEXED_COLUMNS:
            self.assertIn(f"idx_{table}_{column}", indexes)

        # Can be run again
        app_sqlite.create_tables(self.db_file)

        with app_sqlite.get_db_connection() as conn:
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], 'wal')
            # NORMAL
            self.assertEqual(conn.execute("PRAGMA synchronous").fetchone()[0], 1)



    def test_enable_wal_fallback(self):

        with patch.object(app_sqlite, 'get_db_connection', side_effect=sqlite3.OperationalError('database is locked')), \
             self.assertLogs(level='WARNING') as logs:
            self.assertFalse(app_sqlite.enable_wal(self.db_file))

        self.assertIn('database is locked', logs.output[0])



if __name__ == '__main__':
    unittest.main()
