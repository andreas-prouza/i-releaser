import unittest, sys, os, logging, signal, subprocess, tempfile, shutil, time
from unittest.mock import patch

# The repository root, so `etc` and `modules` are found
sys.path.insert(0, os.path.realpath(f"{os.path.dirname(__file__)}/.."))

from etc import constants
# Before meta_file (circular import)
from modules import deploy_version
from modules import current_user, meta_file, workflow, processing_service, stage_status
from modules.db import app_sqlite, meta_file_data, processing_job_data, processing_user_data
from modules.job_status import Status as Job_Status
from modules.meta_file_status import Meta_file_status



WORKFLOW = {
    'name': 'service_wf',
    'default_project': 'service',
    'step_action': [
        {'processing_step': 'ok', 'environment': 'PASE', 'execute': 'echo ok', 'check_error': True},
        {'processing_step': 'broken', 'environment': 'PASE', 'execute': 'echo broken >&2; exit 1', 'check_error': True},
    ],
    'stages': [
        {'name': 'START', 'processing_steps': ['ok'], 'next_stages': ['BROKEN']},
        {'name': 'BROKEN', 'processing_steps': ['broken'], 'next_stages': ['END']},
        {'name': 'END', 'processing_steps': ['ok']},
    ],
}

IMMEDIATE_WORKFLOW = {
    'name': 'immediate_wf',
    'default_project': 'immediate',
    'step_action': [
        {'processing_step': 'ok', 'environment': 'PASE', 'execute': 'echo ok', 'check_error': True},
    ],
    'stages': [
        {'name': 'START', 'processing_steps': ['ok'], 'next_stages': ['NEXT']},
        {'name': 'NEXT', 'processing_steps': ['ok'], 'next_stages': ['END'], 'run_immediate': True},
        {'name': 'END', 'processing_steps': ['ok']},
    ],
}

SLOW_WORKFLOW = {
    'name': 'slow_wf',
    'default_project': 'slow',
    'step_action': [
        {'processing_step': 'slow', 'environment': 'PASE', 'execute': 'sleep 60', 'check_error': True},
    ],
    'stages': [
        {'name': 'START', 'processing_steps': ['slow'], 'next_stages': ['END']},
        {'name': 'END'},
    ],
}



class TestProcessingService(unittest.TestCase):


    def setUp(self):

        self.tmp_dir = tempfile.mkdtemp()
        self.db_file = os.path.join(self.tmp_dir, 'app.sqlite')

        # All modules use the default parameter of get_db_connection
        self.db_defaults = app_sqlite.get_db_connection.__defaults__
        app_sqlite.get_db_connection.__defaults__ = (self.db_file,)
        app_sqlite.create_tables(self.db_file)

        self.patches = [
            patch.object(constants, 'C_META_DIR', os.path.join(self.tmp_dir, 'meta', '{project}', '{create_date}', '{deploy_version}')),
            patch.object(constants, 'C_SERVICE_SOCKET', os.path.join(self.tmp_dir, 'processing-service.sock')),
            patch.object(constants, 'C_SERVICE_PID_FILE', os.path.join(self.tmp_dir, 'processing-service.pid')),
            patch.object(constants, 'C_PROCESSING_MODE', 'service'),
            patch.object(workflow.Workflow, 'get_default_step_mapping', return_value=[]),
        ]
        for p in self.patches:
            p.start()

        current_user.set_user('ALICE')

        self.root_logger = logging.getLogger()
        self.root_level = self.root_logger.level
        self.root_logger.setLevel(logging.INFO)
        self.null_handler = logging.NullHandler()
        self.root_logger.addHandler(self.null_handler)

        self.service = None
        self.projects = 0


    def tearDown(self):

        if self.service is not None:
            for pid in self.service.children:
                self.kill_job_process(pid)
            self.service.stop()

        self.root_logger.removeHandler(self.null_handler)
        self.root_logger.setLevel(self.root_level)

        current_user.set_user(None)

        for p in reversed(self.patches):
            p.stop()

        app_sqlite.get_db_connection.__defaults__ = self.db_defaults
        shutil.rmtree(self.tmp_dir, ignore_errors=True)


    def create_meta_file(self, wf: dict=WORKFLOW) -> meta_file.Meta_File:

        # Deployments of the same project can't be run in parallel
        self.projects += 1
        wf = dict(wf, default_project=f"{wf['default_project']}{self.projects}")

        # The workflow is stored with the deployment
        with patch.object(workflow.Workflow, 'get_workflow_by_name', return_value=workflow.Workflow(dict=wf)):
            mf = meta_file_data.create_new_meta_file(workflow_name=wf['name'])
        mf.set_status(Meta_file_status.READY)
        return mf


    def get_stage(self, mf: meta_file.Meta_File, name: str='START'):
        return meta_file_data.get_meta_file_by_id(mf.id).get_stages_by_name(name)[0]


    def start_service(self) -> processing_service.Service:
        self.service = processing_service.Service()
        self.service.start()
        return self.service


    def kill_job_process(self, pid: int) -> None:
        # A job process is the leader of its own process group, which includes the commands of its steps
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


    def wait_for(self, condition, timeout: float=20) -> bool:

        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if condition():
                return True
            time.sleep(0.05)
        return False


    def get_dead_pid(self) -> int:
        p = subprocess.Popen(['true'])
        p.wait()
        return p.pid



    def test_run_job(self):

        mf = self.create_meta_file()
        job = mf.run_current_stage_as_job(self.get_stage(mf).id)

        self.assertEqual(job.status, Job_Status.QUEUED)
        self.assertEqual(job.user, 'ALICE')
        self.assertEqual([j.id for j in meta_file_data.get_meta_file_by_id(mf.id).processing_jobs], [job.id])

        # Another user is using the web app meanwhile
        current_user.set_user('BOB')

        self.assertEqual(processing_service.run_job(job.id), Job_Status.FINISHED)

        job = processing_job_data.get_job(job.id)
        self.assertEqual(job.status, Job_Status.FINISHED)
        self.assertEqual(job.pid, os.getpid())
        self.assertIsNone(job.error)
        self.assertIsNotNone(job.end_time)

        loaded = meta_file_data.get_meta_file_by_id(mf.id)
        self.assertEqual(loaded.get_stages_by_name('START')[0].status, stage_status.Status.FINISHED)
        self.assertEqual(loaded.status, Meta_file_status.READY)
        self.assertEqual(loaded.processing_jobs, [])

        runs = [u for u in processing_user_data.get_processing_user_by_meta_id(mf.id) if u['action'] == 'run_stage']
        self.assertEqual([u['user'] for u in runs], ['ALICE'])



    def test_run_job_failed(self):

        mf = self.create_meta_file()
        processing_service.run_job(mf.run_current_stage_as_job(self.get_stage(mf).id).id)

        mf = meta_file_data.get_meta_file_by_id(mf.id)
        job = mf.run_current_stage_as_job(self.get_stage(mf, 'BROKEN').id)

        self.assertEqual(processing_service.run_job(job.id), Job_Status.FAILED)

        job = processing_job_data.get_job(job.id)
        self.assertEqual(job.status, Job_Status.FAILED)
        self.assertIn('broken', job.error)

        loaded = meta_file_data.get_meta_file_by_id(mf.id)
        self.assertEqual(loaded.get_stages_by_name('BROKEN')[0].status, stage_status.Status.FAILED)
        self.assertEqual(loaded.status, Meta_file_status.FAILED)



    def test_run_job_with_immediate_stage(self):

        mf = self.create_meta_file(IMMEDIATE_WORKFLOW)
        job = mf.run_current_stage_as_job(self.get_stage(mf).id)

        self.assertEqual(processing_service.run_job(job.id), Job_Status.FINISHED)

        # The following stage has been run by the same job
        self.assertEqual(self.get_stage(mf, 'NEXT').status, stage_status.Status.FINISHED)
        self.assertEqual(self.get_stage(mf, 'END').status, stage_status.Status.READY)
        self.assertEqual(len(processing_job_data.get_jobs()), 1)

        runs = [u for u in processing_user_data.get_processing_user_by_meta_id(mf.id) if u['action'] == 'run_stage']
        self.assertEqual([(u['stage'], u['user']) for u in runs], [('START', 'ALICE'), ('NEXT', 'ALICE')])



    def test_run_job_of_missing_meta_file(self):

        job = processing_job_data.create_job(meta_file_id=4711, stage_id=1)

        self.assertEqual(processing_service.run_job(job.id), Job_Status.FAILED)
        self.assertIn('4711', processing_job_data.get_job(job.id).error)
        self.assertRaises(Exception, processing_service.run_job, 4712)



    def test_stage_is_queued_only_once(self):

        mf = self.create_meta_file()
        start = self.get_stage(mf)
        job = mf.run_current_stage_as_job(start.id)

        with self.assertRaises(Exception) as e:
            mf.run_current_stage_as_job(start.id)
        self.assertIn(f"job {job.id}", str(e.exception))

        # Like a deployment which is in process
        self.assertRaises(Exception, mf.run_current_stage_as_job, self.get_stage(mf, 'BROKEN').id)

        mf.parallel_deployment_execution_allowed = True
        self.assertRaises(Exception, mf.run_current_stage_as_job, start.id)
        mf.check_no_active_job(self.get_stage(mf, 'BROKEN').id)
        mf.parallel_deployment_execution_allowed = False

        self.assertTrue(processing_job_data.cancel_job(job.id))
        self.assertFalse(processing_job_data.cancel_job(job.id))
        self.assertEqual(processing_job_data.get_job(job.id).status, Job_Status.CANCELED)

        mf.run_current_stage_as_job(start.id)
        self.assertEqual(len(processing_job_data.get_active_jobs(mf.id)), 1)



    def test_job_is_claimed_only_once(self):

        first = self.create_meta_file()
        second = self.create_meta_file()
        canceled = self.create_meta_file()

        jobs = [mf.run_current_stage_as_job(self.get_stage(mf).id) for mf in [first, canceled, second]]
        self.assertEqual(processing_job_data.cancel_queued_jobs(canceled.id), 1)

        claimed = processing_job_data.claim_next_job()
        self.assertEqual(claimed.id, jobs[0].id)
        self.assertEqual(claimed.status, Job_Status.RUNNING)
        self.assertIsNotNone(claimed.start_time)
        self.assertIsNotNone(claimed.heartbeat)
        self.assertIsNone(claimed.pid)

        # A running job can't be removed from the queue
        self.assertFalse(processing_job_data.cancel_job(claimed.id))
        self.assertEqual(processing_job_data.cancel_queued_jobs(first.id), 0)

        self.assertEqual(processing_job_data.claim_next_job().id, jobs[2].id)
        self.assertIsNone(processing_job_data.claim_next_job())



    def test_recover_orphans(self):

        mf = self.create_meta_file()
        job = mf.run_current_stage_as_job(self.get_stage(mf).id)
        processing_job_data.claim_next_job()

        # Its process is going to be started
        self.assertEqual(processing_service.recover_orphans(), [])

        # Its process is running
        processing_job_data.set_job_pid(job.id, os.getpid())
        self.assertEqual(processing_service.recover_orphans(), [])

        # The stage was in process, when the job process died
        mf = meta_file_data.get_meta_file_by_id(mf.id)
        mf.get_stages_by_name('START')[0].set_status(stage_status.Status.IN_PROCESS)
        mf.set_status(Meta_file_status.IN_PROCESS)
        processing_job_data.set_job_pid(job.id, self.get_dead_pid())

        with patch.object(processing_service.hooks, 'emit') as emit:
            self.assertEqual([j.id for j in processing_service.recover_orphans()], [job.id])

        emit.assert_called_once()
        self.assertEqual(emit.call_args.args[0], processing_service.hooks.Event.STAGE_FAILED)

        job = processing_job_data.get_job(job.id)
        self.assertEqual(job.status, Job_Status.FAILED)
        self.assertIn("doesn't exist anymore", job.error)

        loaded = meta_file_data.get_meta_file_by_id(mf.id)
        self.assertEqual(loaded.get_stages_by_name('START')[0].status, stage_status.Status.FAILED)
        self.assertEqual(loaded.status, Meta_file_status.FAILED)

        # It can be run again
        loaded.set_status(Meta_file_status.READY)
        loaded.run_current_stage_as_job(loaded.get_stages_by_name('START')[0].id)



    def test_recover_job_without_sign_of_life(self):

        mf = self.create_meta_file()
        job = mf.run_current_stage_as_job(self.get_stage(mf).id)
        processing_job_data.claim_next_job()
        processing_job_data.set_job_pid(job.id, os.getpid())

        with patch.object(constants, 'C_SERVICE_HEARTBEAT_TIMEOUT', -1):
            self.assertEqual([j.id for j in processing_service.recover_orphans()], [job.id])

        self.assertIn('No sign of life', processing_job_data.get_job(job.id).error)



    def test_heartbeat(self):

        mf = self.create_meta_file()
        job = mf.run_current_stage_as_job(self.get_stage(mf).id)
        claimed = processing_job_data.claim_next_job()

        time.sleep(0.01)
        processing_job_data.touch_heartbeat(job.id)

        self.assertGreater(processing_job_data.get_job(job.id).heartbeat, claimed.heartbeat)
        self.assertAlmostEqual(processing_job_data.get_job(job.id).heartbeat, time.time(), delta=5)



    def test_notify(self):

        self.assertFalse(processing_service.notify())

        service = self.start_service()
        self.assertTrue(processing_service.notify())
        self.assertEqual(int(open(constants.C_SERVICE_PID_FILE).read()), os.getpid())

        # Only one service
        self.assertRaises(processing_service.ServiceAlreadyRunningException, processing_service.Service().start)

        service.stop()
        self.service = None
        self.assertFalse(processing_service.notify())
        self.assertFalse(os.path.exists(constants.C_SERVICE_SOCKET))
        self.assertFalse(os.path.exists(constants.C_SERVICE_PID_FILE))

        # Left over of a killed service
        open(constants.C_SERVICE_SOCKET, 'w').close()
        self.assertFalse(processing_service.notify())
        self.start_service()
        self.assertTrue(processing_service.notify())



    def test_long_socket_path(self):

        # Longer than a unix socket path can be
        socket_dir = os.path.join(self.tmp_dir, 'x' * 60, 'y' * 60)
        os.makedirs(os.path.join(socket_dir, 'webapp'))
        cwd = os.getcwd()

        try:
            # Like the service and the web app
            os.chdir(os.path.join(socket_dir, 'webapp'))

            with patch.object(constants, 'C_SERVICE_SOCKET', os.path.join(socket_dir, 'var', 'processing-service.sock')):
                self.assertEqual(processing_service.get_socket_address(), '../var/processing-service.sock')
                self.assertFalse(processing_service.notify())

                service = self.start_service()
                self.assertTrue(os.path.exists(constants.C_SERVICE_SOCKET))
                self.assertTrue(processing_service.notify())

                service.stop()
                self.service = None
                self.assertFalse(os.path.exists(constants.C_SERVICE_SOCKET))
        finally:
            os.chdir(cwd)



    def test_start_stage_as_thread(self):

        mf = self.create_meta_file()
        start = self.get_stage(mf)

        with patch.object(constants, 'C_PROCESSING_MODE', 'thread'), \
             patch.object(meta_file.Meta_File, 'run_current_stage_as_thread') as as_thread:
            self.assertEqual(mf.start_stage(start.id, continue_run=False), {'mode': 'thread'})

        as_thread.assert_called_once_with(start.id, None, False)
        self.assertEqual(processing_job_data.get_jobs(), [])

        with patch.object(constants, 'C_PROCESSING_MODE', 'unknown'):
            self.assertRaises(Exception, mf.start_stage, start.id)



    def test_start_stage_without_service(self):

        mf = self.create_meta_file()
        signature = meta_file_data.get_meta_file_by_id(mf.id).get_state_signature()

        result = mf.start_stage(self.get_stage(mf).id, continue_run=False)

        self.assertEqual(result['mode'], 'service')
        self.assertFalse(result['service_running'])

        job = processing_job_data.get_job(result['job_id'])
        self.assertEqual(job.status, Job_Status.QUEUED)
        self.assertFalse(job.continue_run)

        # The web app shows the queued stage
        loaded = meta_file_data.get_meta_file_by_id(mf.id)
        self.assertEqual(loaded.get_all_data_as_dict()['processing_jobs'][0]['status'], 'queued')
        self.assertNotEqual(loaded.get_state_signature()['page'], signature['page'])
        self.assertEqual(loaded.get_state_signature()['stages'], signature['stages'])



    def test_service_runs_queued_job(self):

        mf = self.create_meta_file()

        # Queued while the service was not running
        waiting = self.create_meta_file()
        waiting_job = waiting.run_current_stage_as_job(self.get_stage(waiting).id)

        service = self.start_service()
        result = mf.start_stage(self.get_stage(mf).id)
        self.assertTrue(result['service_running'])

        # It's woken up by start_stage
        started = time.monotonic()
        service.run_once(timeout=30)
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(len(service.children), 2)

        def all_finished():
            service.run_once(timeout=0.1)
            return len(service.children) == 0

        self.assertTrue(self.wait_for(all_finished))

        for job_id, deployment in [(result['job_id'], mf), (waiting_job.id, waiting)]:
            job = processing_job_data.get_job(job_id)
            self.assertEqual(job.status, Job_Status.FINISHED)
            self.assertNotEqual(job.pid, os.getpid())
            self.assertEqual(self.get_stage(deployment).status, stage_status.Status.FINISHED)

        runs = [u for u in processing_user_data.get_processing_user_by_meta_id(mf.id) if u['action'] == 'run_stage']
        self.assertEqual([u['user'] for u in runs], ['ALICE'])



    def test_job_process_runs_parallel_steps(self):

        # Only succeeds, if both steps run at the same time
        meet = f"touch {self.tmp_dir}/step_$$; for i in $(seq 200); do [ $(ls {self.tmp_dir}/step_* | wc -l) -ge 2 ] && exit 0; sleep 0.02; done; exit 1"

        wf = {
            'name': 'parallel_wf',
            'default_project': 'parallel',
            'step_action': [
                {'processing_step': 'one', 'environment': 'PASE', 'execute': meet, 'parallel_group': 'group', 'parallel': True},
                {'processing_step': 'two', 'environment': 'PASE', 'execute': meet, 'parallel_group': 'group', 'parallel': True},
            ],
            'stages': [
                {'name': 'START', 'processing_steps': ['one', 'two'], 'next_stages': ['END']},
                {'name': 'END'},
            ],
        }

        mf = self.create_meta_file(wf)
        service = self.start_service()
        result = mf.start_stage(self.get_stage(mf).id)

        service.run_once(timeout=30)

        def all_finished():
            service.run_once(timeout=0.1)
            return len(service.children) == 0

        self.assertTrue(self.wait_for(all_finished))

        job = processing_job_data.get_job(result['job_id'])
        self.assertIsNone(job.error)
        self.assertEqual(job.status, Job_Status.FINISHED)
        self.assertNotEqual(job.pid, os.getpid())
        self.assertEqual(self.get_stage(mf).status, stage_status.Status.FINISHED)



    def test_service_respects_max_parallel_jobs(self):

        deployments = [self.create_meta_file(SLOW_WORKFLOW) for _ in range(3)]
        for mf in deployments:
            mf.run_current_stage_as_job(self.get_stage(mf).id)

        service = self.start_service()

        with patch.object(constants, 'C_SERVICE_MAX_PARALLEL_JOBS', 2):
            service.run_once(timeout=0)
            service.run_once(timeout=0)

        self.assertEqual(len(service.children), 2)
        self.assertEqual([j.status for j in processing_job_data.get_jobs()], [Job_Status.RUNNING, Job_Status.RUNNING, Job_Status.QUEUED])



    def test_service_aborts_job_of_killed_process(self):

        mf = self.create_meta_file(SLOW_WORKFLOW)
        service = self.start_service()
        result = mf.start_stage(self.get_stage(mf).id)

        service.run_once(timeout=30)
        pid = next(iter(service.children))

        self.assertTrue(self.wait_for(lambda: self.get_stage(mf).status == stage_status.Status.IN_PROCESS))
        self.assertEqual(processing_job_data.get_job(result['job_id']).pid, pid)

        # Still running after the service has been restarted
        service.stop()
        restarted = processing_service.Service()
        restarted.start()
        restarted.run_once(timeout=0)
        restarted.stop()
        self.assertEqual(processing_job_data.get_job(result['job_id']).status, Job_Status.RUNNING)
        service.start()

        self.kill_job_process(pid)

        def aborted():
            service.run_once(timeout=0.1)
            return processing_job_data.get_job(result['job_id']).status == Job_Status.FAILED

        self.assertTrue(self.wait_for(aborted))
        self.assertEqual(service.children, {})
        self.assertIn('ended unexpectedly (signal 9)', processing_job_data.get_job(result['job_id']).error)

        loaded = meta_file_data.get_meta_file_by_id(mf.id)
        self.assertEqual(loaded.get_stages_by_name('START')[0].status, stage_status.Status.FAILED)
        self.assertEqual(loaded.status, Meta_file_status.FAILED)



if __name__ == '__main__':
    unittest.main()
