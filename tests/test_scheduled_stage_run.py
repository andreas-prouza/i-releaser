"""Scheduled run of a stage (docs/features/scheduled-stage-run.md): the queue, the job process and the service"""
import datetime, logging, os, shutil, signal, sqlite3, sys, tempfile, time, unittest
from unittest.mock import patch

# The repository root, so `etc` and `modules` are found
sys.path.insert(0, os.path.realpath(f"{os.path.dirname(__file__)}/.."))

from etc import constants
import db_tools
# Before meta_file (circular import)
from modules import current_user, errors, hooks, meta_file, processing_job, processing_service, stage_status, workflow
from modules.db import app_sqlite, meta_file_data, processing_job_data, processing_user_data
from modules.db.updates import v_4_1_0
from modules.job_status import Status as Job_Status
from modules.meta_file_status import Meta_file_status
import permission_tools


UTC = datetime.timezone.utc

WORKFLOW = {
    'name': 'schedule_wf',
    'default_project': 'schedule',
    'hooks': {'scheduled_run_failed': ['notify.on_event'], 'stage_failed': ['notify.on_event']},
    'step_action': [
        {'processing_step': 'ok', 'environment': 'PASE', 'execute': 'echo ok', 'check_error': True},
    ],
    'stages': [
        {'name': 'START', 'processing_steps': ['ok'], 'next_stages': ['PROD']},
        {'name': 'PROD', 'processing_steps': ['ok'], 'next_stages': ['END']},
        {'name': 'END'},
    ],
}


def in_minutes(minutes: float) -> datetime.datetime:
    return datetime.datetime.now(UTC) + datetime.timedelta(minutes=minutes)



class TestParseRunAt(unittest.TestCase):


    def test_valid_times(self):

        future = in_minutes(60).replace(microsecond=0)

        for text in [future.isoformat(),
                     future.astimezone(datetime.timezone(datetime.timedelta(hours=9))).isoformat(),
                     future.astimezone(datetime.timezone(datetime.timedelta(hours=-5, minutes=-30))).isoformat(),
                     future.strftime('%Y-%m-%dT%H:%M:%SZ'),
                     f"  {future.isoformat()}  "]:
            with self.subTest(text=text):
                run_at = processing_job.parse_run_at(text)
                self.assertEqual(run_at, future)
                self.assertEqual(run_at.utcoffset(), datetime.timedelta(0))


    def test_invalid_times(self):

        past = in_minutes(-1)
        future = in_minutes(60)

        for value, message in [
            (future.replace(tzinfo=None).isoformat(), 'time zone offset'),
            (past.isoformat(), 'in the past'),
            ('tomorrow at 10', 'not a valid date'),
            ('2026-13-40T25:00:00+01:00', 'not a valid date'),
            ('', 'needs to be'),
            (1764000000, 'needs to be'),
            (None, 'needs to be'),
        ]:
            with self.subTest(value=value):
                with self.assertRaises(errors.Invalid_Input_Error) as e:
                    processing_job.parse_run_at(value)
                self.assertIn(message, str(e.exception))


    def test_stored_form_can_be_compared_as_text(self):

        early = datetime.datetime(2026, 11, 24, 23, 59, 59, 999999, tzinfo=datetime.timezone(datetime.timedelta(hours=1)))
        late = datetime.datetime(2026, 11, 24, 23, 5, tzinfo=UTC)

        self.assertEqual(processing_job.format_utc(early), '2026-11-24T22:59:59+00:00')
        self.assertLess(processing_job.format_utc(early), processing_job.format_utc(late))
        self.assertEqual(processing_job.format_utc_text(late), '2026-11-24 23:05 UTC')


    def test_hook_event_is_valid(self):

        hooks.validate({'scheduled_run_failed': ['notify.on_event']})



class TestScheduledRun(unittest.TestCase):


    def setUp(self):

        db_tools.use_temp_db(self)

        self.patches = [
            patch.object(constants, 'C_SERVICE_SOCKET', os.path.join(self.tmp_dir, 'processing-service.sock')),
            patch.object(constants, 'C_SERVICE_PID_FILE', os.path.join(self.tmp_dir, 'processing-service.pid')),
            patch.object(constants, 'C_SERVICE_LOCK_FILE', os.path.join(self.tmp_dir, 'processing-service.lock')),
            patch.object(constants, 'C_PROCESSING_MODE', 'service'),
            patch.object(constants, 'C_APP_SETTINGS_FILE', os.path.join(self.tmp_dir, 'app.json')),
            patch.object(workflow.Workflow, 'get_default_step_mapping', return_value=[]),
        ]
        for p in self.patches:
            p.start()

        # The hooks which are called: (event, stage name)
        self.events = []
        self.hook_patch = patch.object(hooks, 'resolve', return_value=lambda event, mf, stage: self.events.append((event, stage.name if stage else None)))
        self.hook_patch.start()

        current_user.set_user('ALICE')
        # A job checks the permission of its user when it starts (docs/bugfixes/scheduled-run-without-permission-check.md)
        self.permissions = permission_tools.use_permissions(self.tmp_dir, {'alice': ['read', 'run'], 'bob': ['read', 'run']})

        self.root_logger = logging.getLogger()
        self.null_handler = logging.NullHandler()
        self.root_logger.addHandler(self.null_handler)

        self.service = None
        self.projects = 0


    def tearDown(self):

        if self.service is not None:
            for pid in self.service.children:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self.service.stop()

        self.root_logger.removeHandler(self.null_handler)
        current_user.set_user(None)
        permission_tools.stop_permissions(self.permissions)

        self.hook_patch.stop()
        for p in reversed(self.patches):
            p.stop()



    def create_meta_file(self, wf: dict=WORKFLOW) -> meta_file.Meta_File:

        # Deployments of the same project can't be run in parallel
        self.projects += 1
        wf = dict(wf, default_project=f"{wf['default_project']}{self.projects}")

        with patch.object(workflow.Workflow, 'get_workflow_by_name', return_value=workflow.Workflow(dict=wf)):
            mf = meta_file_data.create_new_meta_file(workflow_name=wf['name'])
        mf.set_status(Meta_file_status.READY)
        return mf


    def get_stage(self, mf: meta_file.Meta_File, name: str='START'):
        return meta_file_data.get_meta_file_by_id(mf.id).get_stages_by_name(name)[0]


    def reload(self, mf: meta_file.Meta_File) -> meta_file.Meta_File:
        return meta_file_data.get_meta_file_by_id(mf.id)


    def schedule(self, mf: meta_file.Meta_File, stage: str='START', minutes: float=60, continue_run: bool=True) -> processing_job.Processing_Job:
        return mf.run_current_stage_as_job(self.get_stage(mf, stage).id, continue_run=continue_run, run_at=in_minutes(minutes))


    def move_run_at(self, job_id: int, minutes: float) -> None:
        """As if the time had passed: the job is due `minutes` ago (negative: in the future)"""
        with app_sqlite.get_db_connection() as conn:
            conn.execute("UPDATE processing_jobs SET run_at = ? WHERE id = ?", (processing_job.format_utc(in_minutes(-minutes)), job_id))
            conn.commit()


    def history(self, mf: meta_file.Meta_File, action: str) -> list[dict]:
        return [row for row in processing_user_data.get_processing_user_by_meta_id(mf.id) if row['action'] == action]


    def wait_for(self, condition, timeout: float=20) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if condition():
                return True
            time.sleep(0.05)
        return False



    def test_scheduled_job_is_stored_in_utc(self):

        mf = self.create_meta_file()
        run_at = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).replace(microsecond=0) + datetime.timedelta(hours=2)

        result = mf.start_stage(self.get_stage(mf).id, run_at=run_at)

        job = processing_job_data.get_job(result['job_id'])
        self.assertEqual(job.status, Job_Status.QUEUED)
        self.assertEqual(job.run_at, run_at)
        self.assertEqual(job.run_at.utcoffset(), datetime.timedelta(0))
        self.assertEqual(result['run_at'], processing_job.format_utc(run_at))
        self.assertEqual(job.get_dict()['run_at'], processing_job.format_utc(run_at))
        self.assertTrue(job.is_waiting_for_its_time())

        # The stage isn't touched until then
        self.assertEqual(self.get_stage(mf).status, stage_status.Status.READY)

        scheduled = self.history(mf, 'schedule_stage')
        self.assertEqual(len(scheduled), 1)
        self.assertEqual((scheduled[0]['user'], scheduled[0]['stage']), ('ALICE', 'START'))
        self.assertIn(processing_job.format_utc_text(run_at), scheduled[0]['details'])
        self.assertIn(f"job {job.id}", scheduled[0]['details'])



    def test_job_is_not_claimed_before_its_time(self):

        mf = self.create_meta_file()
        job = self.schedule(mf, minutes=60)

        self.assertIsNone(processing_job_data.claim_next_job())
        self.assertEqual(processing_job_data.get_job(job.id).status, Job_Status.QUEUED)

        # One second before
        self.move_run_at(job.id, -1 / 60)
        self.assertIsNone(processing_job_data.claim_next_job())

        self.move_run_at(job.id, 0)
        claimed = processing_job_data.claim_next_job()
        self.assertEqual(claimed.id, job.id)
        self.assertEqual(claimed.status, Job_Status.RUNNING)



    def test_scheduled_job_does_not_block_the_queue(self):

        later = self.create_meta_file()
        scheduled = self.schedule(later, minutes=60)

        now = self.create_meta_file()
        immediate = now.run_current_stage_as_job(self.get_stage(now).id)

        self.assertEqual(processing_job_data.claim_next_job().id, immediate.id)
        self.assertIsNone(processing_job_data.claim_next_job())
        self.assertEqual(processing_job_data.get_job(scheduled.id).status, Job_Status.QUEUED)



    def test_scheduled_run(self):

        mf = self.create_meta_file()
        job = self.schedule(mf, minutes=60)

        # Someone else uses the web app meanwhile
        current_user.set_user('BOB')
        self.move_run_at(job.id, 0.5)

        self.assertEqual(processing_job_data.claim_next_job().id, job.id)
        self.assertEqual(processing_service.run_job(job.id), Job_Status.FINISHED)

        job = processing_job_data.get_job(job.id)
        self.assertEqual(job.status, Job_Status.FINISHED)
        self.assertIsNone(job.error)
        self.assertEqual(self.get_stage(mf).status, stage_status.Status.FINISHED)
        self.assertEqual(self.get_stage(mf, 'PROD').status, stage_status.Status.READY)

        # In the name of the user who scheduled it, with the time it was scheduled for
        runs = self.history(mf, 'run_stage')
        self.assertEqual([(r['user'], r['stage']) for r in runs], [('ALICE', 'START')])
        self.assertIn(processing_job.format_utc_text(job.run_at), runs[0]['details'])
        self.assertEqual(self.events, [])



    def test_run_of_a_user_without_permission_anymore(self):
        """docs/bugfixes/scheduled-run-without-permission-check.md"""

        mf = self.create_meta_file()
        job = self.schedule(mf, minutes=60)

        # The user loses the permission `run` before the time of the run
        permission_tools.stop_permissions(self.permissions)
        self.permissions = permission_tools.use_permissions(self.tmp_dir, {'alice': ['read'], 'bob': ['read', 'run']})
        self.move_run_at(job.id, 0.5)

        self.assertEqual(processing_job_data.claim_next_job().id, job.id)
        self.assertEqual(processing_service.run_job(job.id), Job_Status.FAILED)

        job = processing_job_data.get_job(job.id)
        self.assertIn("has no permission 'run'", job.error)
        self.assertEqual(self.get_stage(mf).status, stage_status.Status.READY)
        self.assertEqual(len(self.history(mf, 'scheduled_run_failed')), 1)



    def test_queued_run_of_a_removed_user(self):

        mf = self.create_meta_file()
        job = mf.run_current_stage_as_job(self.get_stage(mf).id)

        permission_tools.stop_permissions(self.permissions)
        self.permissions = permission_tools.use_permissions(self.tmp_dir, {'bob': ['read', 'run']})

        self.assertEqual(processing_job_data.claim_next_job().id, job.id)
        self.assertEqual(processing_service.run_job(job.id), Job_Status.FAILED)
        self.assertEqual(self.get_stage(mf).status, stage_status.Status.READY)
        self.assertIn('Not run', self.history(mf, 'run_stage')[-1]['details'])



    def test_scheduled_run_with_run_all(self):

        mf = self.create_meta_file()
        job = self.schedule(mf, minutes=60, continue_run=False)

        self.assertFalse(processing_job_data.get_job(job.id).continue_run)
        self.assertIn('run all steps', self.history(mf, 'schedule_stage')[0]['details'])

        self.move_run_at(job.id, 0)
        with patch.object(meta_file.Meta_File, 'run_current_stage') as run:
            self.assertEqual(processing_service.run_job(job.id), Job_Status.FINISHED)

        run.assert_called_once_with(self.get_stage(mf).id, None, False, claimed=True)



    def test_missed_time(self):

        mf = self.create_meta_file()
        job = self.schedule(mf, minutes=60)
        self.move_run_at(job.id, constants.C_SCHEDULE_MAX_DELAY_MINUTES + 5)

        self.assertEqual(processing_job_data.claim_next_job().id, job.id)
        self.assertEqual(processing_service.run_job(job.id), Job_Status.FAILED)

        job = processing_job_data.get_job(job.id)
        self.assertEqual(job.status, Job_Status.FAILED)
        self.assertIn('Missed the scheduled time by 65 minutes', job.error)
        self.assertIn('C_SCHEDULE_MAX_DELAY_MINUTES = 60', job.error)

        # Nothing has run
        stage = self.get_stage(mf)
        self.assertEqual(stage.status, stage_status.Status.READY)
        self.assertEqual({a['status'] for a in stage.actions.get_actions_as_dict()}, {'new'})
        self.assertEqual(self.reload(mf).status, Meta_file_status.READY)
        self.assertEqual(self.history(mf, 'run_stage'), [])

        self.assertEqual(self.events, [('scheduled_run_failed', 'START')])
        failed = self.history(mf, 'scheduled_run_failed')
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]['user'], 'ALICE')
        self.assertIn(job.error, failed[0]['details'])

        # It can be run again
        self.reload(mf).run_current_stage_as_job(stage.id)



    def test_late_within_the_limit(self):

        mf = self.create_meta_file()
        job = self.schedule(mf, minutes=60)
        self.move_run_at(job.id, constants.C_SCHEDULE_MAX_DELAY_MINUTES - 1)

        self.assertEqual(processing_service.run_job(job.id), Job_Status.FINISHED)
        self.assertEqual(self.get_stage(mf).status, stage_status.Status.FINISHED)



    def test_no_limit(self):

        mf = self.create_meta_file()
        job = self.schedule(mf, minutes=60)
        self.move_run_at(job.id, 24 * 60)

        with patch.object(constants, 'C_SCHEDULE_MAX_DELAY_MINUTES', 0):
            self.assertEqual(processing_service.run_job(job.id), Job_Status.FINISHED)

        self.assertEqual(self.get_stage(mf).status, stage_status.Status.FINISHED)



    def test_stage_can_not_be_run_at_its_time(self):

        mf = self.create_meta_file()
        job = self.schedule(mf, minutes=60)
        self.move_run_at(job.id, 0.5)

        # Meanwhile the deployment is in process (e.g. its status hangs)
        self.reload(mf).set_status(Meta_file_status.IN_PROCESS)

        self.assertEqual(processing_service.run_job(job.id), Job_Status.FAILED)

        job = processing_job_data.get_job(job.id)
        self.assertTrue(job.error.startswith('The stage could not be run: '), job.error)
        self.assertIn("in process", job.error)
        self.assertEqual(self.get_stage(mf).status, stage_status.Status.READY)

        # The stage hasn't run: no stage_failed
        self.assertEqual(self.events, [('scheduled_run_failed', 'START')])
        self.assertEqual(self.history(mf, 'run_stage'), [])



    def test_hook_reads_the_reason_from_the_job(self):

        mf = self.create_meta_file()
        job = self.schedule(mf, minutes=60)
        self.move_run_at(job.id, 2 * 24 * 60)
        errors_seen = []

        def on_event(event, meta_file, stage):
            errors_seen.append(processing_job_data.get_last_jobs(meta_file.id)[stage.id].error)

        with patch.object(hooks, 'resolve', return_value=on_event):
            processing_service.run_job(job.id)

        self.assertEqual(len(errors_seen), 1)
        self.assertIn('Missed the scheduled time', errors_seen[0])



    def test_cancel_before_its_time(self):

        mf = self.create_meta_file()
        job = self.schedule(mf, minutes=60)

        self.assertTrue(processing_job_data.cancel_job(job.id))
        self.assertEqual(processing_job_data.get_job(job.id).status, Job_Status.CANCELED)

        # At its time nothing happens
        self.move_run_at(job.id, 0)
        self.assertIsNone(processing_job_data.claim_next_job())
        self.assertEqual(self.get_stage(mf).status, stage_status.Status.READY)

        # The stage can be scheduled again or run
        self.schedule(self.reload(mf), minutes=30)



    def test_cancel_of_a_running_job_fails(self):

        mf = self.create_meta_file()
        job = self.schedule(mf, minutes=60)
        self.move_run_at(job.id, 0)
        processing_job_data.claim_next_job()

        self.assertFalse(processing_job_data.cancel_job(job.id))
        self.assertEqual(processing_job_data.get_job(job.id).status, Job_Status.RUNNING)



    def test_deployment_is_blocked_while_a_run_is_scheduled(self):

        mf = self.create_meta_file()
        job = self.schedule(mf, minutes=60)

        with self.assertRaises(errors.Conflict_Error):
            mf.run_current_stage_as_job(self.get_stage(mf, 'PROD').id)
        with self.assertRaises(errors.Conflict_Error):
            self.schedule(mf, minutes=10)

        # Canceling the deployment removes it from the queue
        self.assertEqual(processing_job_data.cancel_queued_jobs(mf.id), 1)
        self.assertEqual(processing_job_data.get_job(job.id).status, Job_Status.CANCELED)



    def test_only_with_the_processing_service(self):

        mf = self.create_meta_file()

        with patch.object(constants, 'C_PROCESSING_MODE', 'thread'):
            with self.assertRaises(errors.Conflict_Error) as e:
                mf.start_stage(self.get_stage(mf).id, run_at=in_minutes(60))

        self.assertIn("mode 'service'", str(e.exception))
        self.assertEqual(processing_job_data.get_jobs(), [])
        self.assertEqual(self.get_stage(mf).status, stage_status.Status.READY)



    def test_last_jobs_of_the_stages(self):

        mf = self.create_meta_file()
        first = self.schedule(mf, minutes=60)
        processing_job_data.cancel_job(first.id)
        second = self.schedule(self.reload(mf), minutes=30)

        last = processing_job_data.get_last_jobs(mf.id)
        self.assertEqual(list(last), [self.get_stage(mf).id])
        self.assertEqual(last[self.get_stage(mf).id].id, second.id)



    def test_service_runs_the_job_at_its_time(self):

        mf = self.create_meta_file()
        job = mf.run_current_stage_as_job(self.get_stage(mf).id, run_at=datetime.datetime.now(UTC) + datetime.timedelta(seconds=2))

        self.service = processing_service.Service()
        self.service.start()

        self.service.run_once(timeout=0)
        self.assertEqual(self.service.children, {})
        self.assertEqual(processing_job_data.get_job(job.id).status, Job_Status.QUEUED)

        def finished():
            self.service.run_once(timeout=0.2)
            return processing_job_data.get_job(job.id).status == Job_Status.FINISHED and not self.service.children

        self.assertTrue(self.wait_for(finished))

        job = processing_job_data.get_job(job.id)
        self.assertGreaterEqual(job.start_time.astimezone(UTC), job.run_at)
        self.assertEqual(self.get_stage(mf).status, stage_status.Status.FINISHED)



class TestDatabaseUpdate(unittest.TestCase):


    def test_add_run_at(self):

        tmp_dir = tempfile.mkdtemp()
        db_file = os.path.join(tmp_dir, 'app.sqlite')
        defaults = app_sqlite.get_db_connection.__defaults__
        app_sqlite.get_db_connection.__defaults__ = (db_file,)

        try:
            with sqlite3.connect(db_file) as conn:
                conn.execute("CREATE TABLE processing_jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT)")
                conn.execute("INSERT INTO processing_jobs (status) VALUES ('finished')")
            conn.close()

            v_4_1_0.add_job_run_at()
            # A second time: nothing happens
            v_4_1_0.add_job_run_at()

            with sqlite3.connect(db_file) as conn:
                columns = [row[1] for row in conn.execute("PRAGMA table_info(processing_jobs)")]
                rows = conn.execute("SELECT status, run_at FROM processing_jobs").fetchall()
            conn.close()

            self.assertIn('run_at', columns)
            self.assertEqual(rows, [('finished', None)])

        finally:
            app_sqlite.get_db_connection.__defaults__ = defaults
            shutil.rmtree(tmp_dir, ignore_errors=True)
