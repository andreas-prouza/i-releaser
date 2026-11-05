"""Workflow files, local settings, templates and object lists"""
import glob, json, os, re, shutil, subprocess, sys, tempfile, unittest
from unittest.mock import patch

from etc import constants
# Before meta_file (circular import)
from modules import deploy_version
from modules import errors, hooks, ibm_i_commands, meta_file, workflow
from modules.db import app_sqlite, meta_file_data
from modules.meta_file_status import Meta_file_status

from web_server import ROOT_DIR, USERS, WORKFLOWS, Web_Server, copy_repository


VALID_WORKFLOW = {
    'name': 'valid_wf',
    'default_project': 'valid',
    'step_action': [{'processing_step': 'step', 'environment': 'PASE', 'execute': 'echo ok', 'check_error': True}],
    'stages': [{'name': 'START', 'processing_steps': ['step'], 'next_stages': ['END']}, {'name': 'END'}],
}



class TestInvalidWorkflowFiles(unittest.TestCase):


    def setUp(self):

        self.directory = tempfile.mkdtemp()

        with open(os.path.join(self.directory, 'valid.json'), 'w') as f:
            json.dump(VALID_WORKFLOW, f)

        with open(os.path.join(self.directory, 'broken.json'), 'w') as f:
            f.write('{ not json')

        with open(os.path.join(self.directory, 'wrong.json'), 'w') as f:
            json.dump({'name': 'wrong_wf'}, f)

        self.patches = [
            patch.object(constants, 'C_WORKFLOWS_DIR', self.directory),
            patch.object(constants, 'C_WORKFLOW', os.path.join(self.directory, 'none')),
            patch.object(workflow.Workflow, 'get_default_step_mapping', return_value=[]),
        ]
        for p in self.patches:
            p.start()


    def tearDown(self):

        for p in reversed(self.patches):
            p.stop()

        shutil.rmtree(self.directory)


    def test_valid_workflows_keep_working(self):

        self.assertEqual([wf['name'] for wf in workflow.Workflow.get_all_workflows_json()], ['valid_wf'])
        self.assertEqual(workflow.Workflow.get_all_projects(), ['valid'])
        self.assertEqual(workflow.Workflow('valid_wf').default_project, 'valid')


    def test_invalid_files_are_listed_with_their_error(self):

        invalid = workflow.Workflow.get_invalid_workflow_files()

        self.assertEqual(sorted(os.path.basename(f) for f in invalid), ['broken.json', 'wrong.json'])
        self.assertIn('default_project', invalid[os.path.join(self.directory, 'wrong.json')])


    def test_error_names_the_invalid_files(self):

        with self.assertRaises(workflow.WorkflowNotFoundException) as e:
            workflow.Workflow('wrong_wf')

        self.assertIn('wrong.json', str(e.exception))


    def test_invalid_old_workflow_file(self):

        with open(constants.C_WORKFLOW, 'w') as f:
            f.write('{ not json')

        self.assertEqual([wf['name'] for wf in workflow.Workflow.get_all_workflows_json()], ['valid_wf'])



class TestWebAppWithInvalidWorkflowFile(unittest.TestCase):


    def test_pages_work_and_admin_sees_the_error(self):

        server = Web_Server()

        with open(os.path.join(server.directory, 'etc', 'workflows', 'broken.json'), 'w') as f:
            f.write('{ not json')

        try:
            server.start()
            boss, intern = server.client('boss'), server.client('intern')

            for path in ['/', '/workflows', '/settings']:
                self.assertEqual(boss.get(path, headers={'Accept': 'text/html'})[0], 200, path)

            self.assertIn('broken.json', boss.get('/workflows', headers={'Accept': 'text/html'})[2])
            self.assertNotIn('broken.json', intern.get('/workflows', headers={'Accept': 'text/html'})[2])

            # A deployment whose workflow file becomes invalid can still run
            deployment = boss.create_deployment('hidden_wf')

            with open(os.path.join(server.directory, 'etc', 'workflows', 'hidden_wf.json'), 'w') as f:
                f.write('{ not json')

            self.assertEqual(boss.run_stage(deployment, 'START')[0], 200)
            self.assertEqual(boss.wait_for_stage(deployment, 'START')['status'], 'finished')

            status, data = boss.post_json('/api/start_workflow/hidden_wf', {})
            self.assertEqual(status, 404)
            self.assertIn('hidden_wf.json', data['message'])

        finally:
            server.close()



class TestLocalSettings(unittest.TestCase):


    def read_setting(self, settings: str|None) -> str:

        directory = tempfile.mkdtemp()

        try:
            os.makedirs(os.path.join(directory, 'etc'))
            shutil.copy(os.path.join(ROOT_DIR, 'etc', 'constants.py'), os.path.join(directory, 'etc', 'constants.py'))

            if settings is not None:
                with open(os.path.join(directory, 'etc', 'settings.py'), 'w') as f:
                    f.write(settings)

            return subprocess.run([sys.executable, '-c', 'from etc import constants; print(constants.C_PROCESSING_MODE)'],
                                  cwd=directory, env={**os.environ, 'PYTHONPATH': directory}, capture_output=True, text=True, check=True).stdout.strip()

        finally:
            shutil.rmtree(directory)


    def test_defaults_without_settings(self):
        self.assertEqual(self.read_setting(None), 'thread')


    def test_settings_override_defaults(self):
        self.assertEqual(self.read_setting("C_PROCESSING_MODE = 'service'\n"), 'service')


    def test_template_changes_nothing(self):

        with open(os.path.join(ROOT_DIR, 'etc', 'examples', 'settings.py')) as f:
            self.assertEqual(self.read_setting(f.read()), 'thread')


    def test_settings_file_is_not_tracked(self):
        self.assertEqual(subprocess.run(['git', 'check-ignore', '-q', 'etc/settings.py'], cwd=ROOT_DIR).returncode, 0)



class Temp_Database(unittest.TestCase):

    WORKFLOW = {}
    OBJECT_COMMANDS = []


    def setUp(self):

        self.tmp_dir = tempfile.mkdtemp()
        self.db_file = os.path.join(self.tmp_dir, 'app.sqlite')
        self.build_dir = os.path.join(self.tmp_dir, 'build')
        os.makedirs(self.build_dir)

        self.db_defaults = app_sqlite.get_db_connection.__defaults__
        app_sqlite.get_db_connection.__defaults__ = (self.db_file,)
        app_sqlite.create_tables(self.db_file)

        commands_file = os.path.join(self.tmp_dir, 'object_commands.json')
        with open(commands_file, 'w') as f:
            json.dump(self.OBJECT_COMMANDS, f)

        self.patches = [
            patch.object(constants, 'C_META_DIR', os.path.join(self.tmp_dir, 'meta', '{project}', '{create_date}', '{deploy_version}')),
            patch.object(constants, 'C_OBJECT_COMMANDS', commands_file),
            patch.object(workflow.Workflow, 'get_workflow_by_name', return_value=workflow.Workflow(dict=self.WORKFLOW)),
            patch.object(workflow.Workflow, 'get_default_step_mapping', return_value=[]),
        ]
        for p in self.patches:
            p.start()


    def tearDown(self):

        for p in reversed(self.patches):
            p.stop()

        app_sqlite.get_db_connection.__defaults__ = self.db_defaults
        shutil.rmtree(self.tmp_dir)


    def write_object_list(self, content: str, name: str='objects.txt') -> str:

        path = os.path.join(self.build_dir, name)
        with open(path, 'w') as f:
            f.write(content)
        return path



class TestObjectList(Temp_Database):

    @property
    def WORKFLOW(self):
        return {**VALID_WORKFLOW, 'stages': [{**VALID_WORKFLOW['stages'][0], 'build_dir': self.build_dir}, VALID_WORKFLOW['stages'][1]]}


    def test_list_in_the_build_dir(self):

        path = self.write_object_list('1|prodlib|devlib|orders|file|pf\n')
        mf = meta_file_data.create_new_meta_file('valid_wf', object_list=path)
        mf.import_objects_from_config_file()

        self.assertEqual([o.name for o in mf.deploy_objects], ['orders'])


    def test_list_outside_of_the_allowed_directories(self):

        link = os.path.join(self.build_dir, 'link')
        os.symlink('/etc/passwd', link)

        for path in ['/etc/passwd', os.path.join(self.build_dir, '..', 'x'), link]:
            with self.assertRaises(errors.Invalid_Input_Error):
                meta_file_data.create_new_meta_file('valid_wf', object_list=path)


    def test_configured_directory(self):

        directory = os.path.join(self.tmp_dir, 'lists')
        os.makedirs(directory)

        with patch.object(constants, 'C_OBJECT_LIST_DIRS', [directory]):
            meta_file_data.create_new_meta_file('valid_wf', object_list=os.path.join(directory, 'a.txt'))


    def test_invalid_line_is_reported_without_its_content(self):

        path = self.write_object_list('1|prodlib|devlib|orders|file|pf\n2|prodlib|devlib|date|srvpgm|rpgle\nroot:x:0:0:root\n')
        mf = meta_file_data.create_new_meta_file('valid_wf', object_list=path)

        with self.assertRaises(Exception) as e:
            mf.import_objects_from_config_file()

        self.assertEqual(str(e.exception), 'Object list: line 3 is invalid')


    def test_import_twice_does_not_duplicate_the_objects(self):

        path = self.write_object_list('1|prodlib|devlib|orders|file|pf\n')
        mf = meta_file_data.create_new_meta_file('valid_wf', object_list=path)
        mf.import_objects_from_config_file()
        mf.import_objects_from_config_file()

        self.assertEqual(len(meta_file_data.get_meta_file_by_id(mf.id).deploy_objects), 1)



class TestObjectCommands(Temp_Database):

    WORKFLOW = {
        'name': 'objects_wf',
        'default_project': 'objects',
        'step_action': [
            {'processing_step': 'load', 'environment': 'SCRIPT', 'execute': 'object_script.load', 'check_error': True},
            {'processing_step': 'deploy', 'environment': 'PASE', 'execute': 'echo deploy', 'check_error': True},
            {'processing_step': 'post', 'environment': 'PASE', 'execute': 'echo post', 'check_error': True},
        ],
        'stages': [
            {'name': 'START', 'processing_steps': ['load', 'deploy'], 'next_stages': ['TEST']},
            {'name': 'TEST', 'processing_steps': ['deploy', 'post'], 'next_stages': ['PROD']},
            {'name': 'PROD', 'processing_steps': ['deploy', 'post'], 'next_stages': ['END']},
            {'name': 'END'},
        ],
    }

    OBJECT_COMMANDS = [
        {'lib': 'PRODLIB', 'name': 'Orders', 'type': 'FILE', 'actions': [
            {'processing_step': 'deploy', 'environment': 'PASE', 'cmd': 'echo all-stages'},
            {'processing_step': 'post', 'environment': 'PASE', 'cmd': 'echo only-prod', 'stages': ['PROD']},
        ]},
        {'lib': 'prodlib', 'name': 'other', 'type': 'pgm', 'actions': [
            {'processing_step': 'deploy', 'environment': 'PASE', 'cmd': 'echo no-such-object'},
        ]},
    ]


    def setUp(self):

        super().setUp()

        path = self.write_object_list('1|prodlib|devlib|orders|file|pf\n')

        with patch.object(constants, 'C_OBJECT_LIST_DIRS', [self.build_dir]):
            self.mf = meta_file_data.create_new_meta_file('objects_wf', object_list=path)

        self.mf.set_status(Meta_file_status.READY)

        from types import SimpleNamespace

        self.loads = 0

        def load(meta_file, stage_obj, action):
            self.loads += 1
            meta_file.import_objects_from_config_file()

        self.script = patch.dict(ibm_i_commands.__dict__, {'object_script': SimpleNamespace(load=load)})
        self.script.start()


    def tearDown(self):
        self.script.stop()
        super().tearDown()


    def reload(self):
        return meta_file_data.get_meta_file_by_id(self.mf.id)


    def get_commands(self, stage: str) -> list[str]:
        return [a.cmd for a in self.reload().get_stages_by_name(stage)[0].actions.get_actions()]


    def run_stage(self, name: str, continue_run=True) -> None:
        mf = self.reload()
        mf.run_current_stage(mf.get_stages_by_name(name)[0].id, continue_run=continue_run)


    def test_commands_are_added_after_their_step(self):

        self.run_stage('START')

        self.assertEqual(self.get_commands('TEST'), ['echo deploy', 'echo all-stages', 'echo post'])
        self.assertEqual(self.get_commands('PROD'), ['echo deploy', 'echo all-stages', 'echo post', 'echo only-prod'])


    def test_commands_run_with_their_own_status(self):

        self.run_stage('START')
        self.run_stage('TEST')

        stage = self.reload().get_stages_by_name('TEST')[0]

        self.assertEqual(stage.status.value, 'finished')
        self.assertEqual({a.status.value for a in stage.actions}, {'finished'})
        self.assertEqual(len(next(a for a in stage.actions if a.cmd == 'echo all-stages').run_history), 1)


    def test_running_stage_gets_its_commands_too(self):

        self.run_stage('START')

        stage = self.reload().get_stages_by_name('START')[0]

        self.assertEqual(stage.status.value, 'finished')
        self.assertEqual(self.get_commands('START'), ['object_script.load', 'echo deploy', 'echo all-stages'])
        self.assertEqual({a.status.value for a in stage.actions}, {'finished'})


    def test_import_again_adds_each_command_once(self):

        self.run_stage('START')

        mf = self.reload()
        mf.import_objects_from_config_file()

        self.assertEqual(self.get_commands('TEST'), ['echo deploy', 'echo all-stages', 'echo post'])



class TestCustomData(unittest.TestCase):


    def get_workflow(self, **attributes) -> workflow.Workflow:
        return workflow.Workflow(dict={**VALID_WORKFLOW, **attributes})


    def test_without_create_fields_all_but_protected_fields_are_allowed(self):

        wf = self.get_workflow()
        wf.check_custom_data({'project': 'a', 'version': '1', 'any': {'thing': [1, 2]}})

        with self.assertRaises(errors.Invalid_Input_Error):
            wf.check_custom_data({'db_deployment': {'tables': []}})


    def test_create_fields(self):

        wf = self.get_workflow(create_fields=['$.ticket', '$.jira', '$.db_deployment'])
        wf.check_custom_data({'ticket': 'A', 'jira': {'ticket': 'B', 'x': 1}, 'db_deployment': {'tables': [{'lib': 'A'}]}})

        with self.assertRaises(errors.Invalid_Input_Error) as e:
            wf.check_custom_data({'ticket': 'A', 'other': 'x'})

        self.assertIn('other', str(e.exception))


    def test_nested_create_field(self):

        wf = self.get_workflow(create_fields=['$.jira.ticket'])
        wf.check_custom_data({'jira': {'ticket': 'B'}})

        with self.assertRaises(errors.Invalid_Input_Error):
            wf.check_custom_data({'jira': {'other': 'B'}})


    def test_size_limit(self):

        with patch.object(constants, 'C_MAX_CUSTOM_DATA_SIZE', 10):
            with self.assertRaises(errors.Invalid_Input_Error):
                self.get_workflow().check_custom_data({'a': 'b' * 20})


    def test_workflow_validates_create_fields(self):

        with patch.object(workflow.Workflow, 'get_default_step_mapping', return_value=[]):
            workflow.Workflow.validate_workflow({**VALID_WORKFLOW, 'create_fields': ['$.ticket']}, 'a.json')

            with self.assertRaises(Exception):
                workflow.Workflow.validate_workflow({**VALID_WORKFLOW, 'create_fields': 'ticket'}, 'a.json')



class TestCompileList(Temp_Database):

    # `compiles` doesn't have to be listed: it isn't custom data
    WORKFLOW = {**VALID_WORKFLOW, 'create_fields': ['$.ticket']}
    COMPILES = [{'level': 0, 'sources': [{'source': 'lib/qrpglesrc/pgm.rpgle.pgm', 'absolute_path': '/home/ä/src/pgm.rpgle'}]}]


    def test_stored_in_the_meta_directory(self):

        mf = meta_file_data.create_new_meta_file('valid_wf', custom_data={'ticket': 'A'}, compiles=self.COMPILES)

        self.assertTrue(os.path.isfile(os.path.join(mf.meta_dir, 'compile-list.json')))
        loaded = meta_file_data.get_meta_file_by_id(mf.id)
        self.assertEqual(loaded.get_compile_list(), self.COMPILES)
        self.assertEqual(loaded.custom_data, {'ticket': 'A'})


    def test_older_deployments_have_it_in_custom_data(self):

        mf = meta_file_data.create_new_meta_file('valid_wf')
        self.assertIsNone(mf.get_compile_list())

        mf.custom_data = {'compiles': self.COMPILES}
        self.assertEqual(mf.get_compile_list(), self.COMPILES)


    def test_hook_on_creation_sees_it(self):

        seen = []
        with patch.object(hooks, 'emit', side_effect=lambda event, mf, *args, **kwargs: seen.append(mf.get_compile_list())):
            meta_file_data.create_new_meta_file('valid_wf', compiles=self.COMPILES)

        self.assertEqual(seen, [self.COMPILES])


    def test_size_limit(self):

        with patch.object(constants, 'C_MAX_COMPILE_LIST_SIZE', 10):
            with self.assertRaises(errors.Invalid_Input_Error) as e:
                meta_file_data.create_new_meta_file('valid_wf', compiles=self.COMPILES)

        self.assertIn('limit is 10 bytes', str(e.exception))


    def test_has_to_be_a_list(self):

        with self.assertRaises(errors.Invalid_Input_Error):
            meta_file_data.create_new_meta_file('valid_wf', compiles={'level': 0})



class TestTemplates(unittest.TestCase):


    def setUp(self):
        self.directory = tempfile.mkdtemp()
        copy_repository(self.directory)


    def tearDown(self):
        shutil.rmtree(self.directory)


    def run_python(self, code: str) -> str:
        env = {**os.environ, 'PYTHONPATH': self.directory}
        result = subprocess.run([sys.executable, '-c', code], cwd=os.path.join(self.directory, 'webapp'), env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout


    def test_every_script_step_exists(self):

        result = self.run_python('''
import json
from modules import deploy_version
from modules import hooks, ibm_i_commands
for entry in json.load(open("../etc/examples/default_step_action.json")):
    if entry["environment"] == "SCRIPT":
        assert callable(hooks.resolve(entry["execute"])), entry
print("ok")
''')
        self.assertEqual(result.strip(), 'ok')


    def test_no_duplicate_or_test_entries(self):

        with open(os.path.join(ROOT_DIR, 'etc', 'examples', 'default_step_action.json')) as f:
            steps = [entry['processing_step'] for entry in json.load(f)]

        self.assertEqual(len(steps), len(set(steps)))
        self.assertFalse([s for s in steps if s.startswith('test_')])


    def test_template_workflows_are_valid(self):

        files = glob.glob(os.path.join(ROOT_DIR, 'etc', 'examples', 'workflows', '*.json'))
        self.assertGreater(len(files), 0)

        with open(os.path.join(ROOT_DIR, 'etc', 'examples', 'default_step_action.json')) as f:
            steps = json.load(f)

        with patch.object(workflow.Workflow, 'get_default_step_mapping', return_value=steps):
            for file in files:
                with open(file) as f:
                    workflow.Workflow.validate_workflow(json.load(f), file)


    def test_no_personal_names(self):

        result = subprocess.run(['grep', '-ril', 'prouza', 'etc/examples', 'scripts/examples', 'webapp/etc/examples'], cwd=ROOT_DIR, capture_output=True, text=True)
        self.assertEqual(result.stdout, '')


    def test_templates_are_not_ignored(self):

        for file in ['etc/examples/jira.json', 'etc/examples/db_deployment.json', 'etc/examples/workflows/deploy_2_test.json']:
            self.assertNotEqual(subprocess.run(['git', 'check-ignore', '-q', file], cwd=ROOT_DIR).returncode, 0, file)


    def test_jira_template_is_off(self):

        with open(os.path.join(ROOT_DIR, 'etc', 'examples', 'jira.json')) as f:
            self.assertFalse(json.load(f)['enabled'])


    def test_logger_templates_use_info(self):

        for file in ['etc/examples/logger_config.py', 'webapp/etc/examples/logger_config.py']:
            with open(os.path.join(ROOT_DIR, file)) as f:
                self.assertIn('LOG_LEVEL = logging.INFO', f.read())


    def test_new_installation_runs_a_template_workflow(self):

        server = Web_Server(workflows={}, users={'myuser': {'permissions': {'general': ['read', 'start workflow', 'run'], 'workflows': {}}}})

        workflows_dir = os.path.join(server.directory, 'etc', 'workflows')
        shutil.copy(os.path.join(ROOT_DIR, 'etc', 'examples', 'workflows', 'parallel_example.json'), workflows_dir)

        try:
            server.start()
            client = server.client('myuser')

            deployment = client.create_deployment('parallel_example')
            self.assertEqual(client.run_stage(deployment, 'START')[0], 200)
            self.assertEqual(client.wait_for_stage(deployment, 'START')['status'], 'finished')

        finally:
            server.close()



class TestDeadCode(unittest.TestCase):


    def test_removed_code_is_gone(self):

        names = ['is_backup_name_already_in_use', 'import_objects_from_config_file_old', 'add_object_from_meta_structure', 'get_flowchart_text', 'run_compile_script',
                 'generate_commands', 'C_STAGE_COMMANDS', 'flask_config', 'starsessions', 'function show_json', 'CURRENT_USER', 'XXXXX']

        result = subprocess.run(['grep', '-rnE', '|'.join(names), 'modules', 'webapp/routes', 'webapp/web_modules', 'webapp/templates/overview', 'webapp/index.py', 'scripts/examples', 'etc/examples', 'etc/constants.py', 'requirements.txt'],
                                cwd=ROOT_DIR, capture_output=True, text=True)

        self.assertEqual(result.stdout, '')



class TestStartScript(unittest.TestCase):


    def setUp(self):

        self.server = Web_Server(env={'I_RELEASER_LOCAL_DEBUGGING': 'False'})

        os.symlink(sys.prefix, os.path.join(self.server.directory, '.venv'))

        with open(os.path.join(self.server.web_dir, 'etc', 'gunicorn.conf.py'), 'w') as f:
            f.write(f"bind = '127.0.0.1:{self.server.port}'\nworkers = 1\npidfile = 'etc/webapp.pid'\nworker_class = 'uvicorn.workers.UvicornWorker'\n")

        self.script = os.path.join(self.server.web_dir, 'service')
        self.pid_file = os.path.join(self.server.web_dir, 'etc', 'webapp.pid')


    def tearDown(self):
        self.service('stop')
        self.server.close()


    def service(self, command: str) -> subprocess.CompletedProcess:
        # From another directory
        return subprocess.run(['bash', self.script, command], cwd='/', capture_output=True, text=True, timeout=40, env=self.server.get_environment())


    def test_start_stop_and_crash(self):

        self.assertIn('stopped', self.service('status').stdout)
        self.assertEqual(self.service('stop').returncode, 0)

        result = self.service('start')
        self.assertIn('running', result.stdout, result.stdout + result.stderr)

        with open(self.pid_file) as f:
            pid = int(f.read())

        self.assertIn('already exist', self.service('start').stdout)

        os.kill(pid, 9)

        for _ in range(50):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            import time
            time.sleep(0.1)

        self.assertIn('stopped', self.service('status').stdout)
        self.assertIn('running', self.service('start').stdout)
        self.assertIn('stopped', self.service('stop').stdout)



class TestProcessingServiceDatabaseCheck(unittest.TestCase):


    def test_service_refuses_an_old_database(self):

        server = Web_Server()

        try:
            import sqlite3

            os.makedirs(os.path.join(server.directory, 'log'), exist_ok=True)
            env = {**os.environ}

            # The web app creates the database. Then it becomes old.
            server.start()
            server.stop()

            db = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'))
            db.execute("PRAGMA user_version = 3")
            db.commit()
            db.close()

            result = subprocess.run([sys.executable, os.path.join(server.directory, 'serviceapp', 'service.py')], capture_output=True, text=True, env=env, timeout=30)

            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn('Start the web app first', result.stderr)

        finally:
            server.close()



class TestWebAppIsNotBlocked(unittest.TestCase):


    def test_slow_request_does_not_block_others(self):

        hook_workflow = {**WORKFLOWS['seq_wf'], 'name': 'hook_wf', 'hooks': {'deployment_created': ['slow_hook.wait']}}
        server = Web_Server(workflows={'hook_wf': hook_workflow})

        with open(os.path.join(server.directory, 'scripts', 'slow_hook.py'), 'w') as f:
            f.write("import time\n\ndef wait(event, meta_file, stage_obj):\n    time.sleep(3)\n")

        try:
            server.start()
            boss = server.client('boss')

            import threading, time

            slow = threading.Thread(target=lambda: server.client('boss').create_deployment('hook_wf'))
            slow.start()
            time.sleep(0.5)

            start = time.time()
            self.assertEqual(boss.get('/api/get_workflows')[0], 200)
            elapsed = time.time() - start

            slow.join()
            self.assertLess(elapsed, 1)

        finally:
            server.close()



class TestSessionCleanup(unittest.TestCase):


    def run_in_webapp(self, server: Web_Server, code: str) -> str:
        env = {**server.get_environment(), 'PYTHONPATH': f"{server.directory}:{server.web_dir}"}
        result = subprocess.run([sys.executable, '-c', code], cwd=server.web_dir, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()


    def test_expired_sessions_are_deleted(self):

        server = Web_Server()

        try:
            result = self.run_in_webapp(server, '''
import json, os, uuid
from datetime import datetime, timedelta
from web_modules import server_sessions as s

def write(last_update, create_time=None):
    session_id = str(uuid.uuid4())
    with open(s.get_session_filepath(session_id), "w") as f:
        json.dump({"last-update": last_update.isoformat(), "create-time": (create_time or last_update).isoformat(), "session-data": {"a": 1}}, f)
    return session_id

now = datetime.now()
current = write(now)
idle = write(now - timedelta(hours=2))
too_old = write(now, now - timedelta(hours=13))

other_file = os.path.join(s.SESSION_DIR, "keep.txt")
open(other_file, "w").close()

print(s.delete_expired_sessions(), sorted(os.listdir(s.SESSION_DIR)) == sorted([f"{current}.json", "keep.txt"]))
print(s.load_session_file(current) is not None, s.load_session_file(too_old) is None, s.is_valid_session_id("../x"), s.is_valid_session_id(current))
''')
            self.assertEqual(result.splitlines(), ['2 True', 'True True False True'])

        finally:
            server.close()
