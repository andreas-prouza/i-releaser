"""Scheduled run of a stage through the web app (docs/features/scheduled-stage-run.md), tested against the running application"""
import datetime, html, json, os, re, sqlite3, subprocess, sys, time

import pytest

from web_server import Web_Server


HTML = {'Accept': 'text/html'}
UTC = datetime.timezone.utc


@pytest.fixture(scope='module')
def server():
    # Mode service, but no service: the scheduled runs stay in the queue
    s = Web_Server(settings="C_PROCESSING_MODE = 'service'\n").start()
    yield s
    s.close()


@pytest.fixture()
def boss(server):
    return server.client('boss')


def in_minutes(minutes: float, offset_hours: float=1) -> str:
    """ISO time with offset, as the browser sends it"""
    zone = datetime.timezone(datetime.timedelta(hours=offset_hours))
    return (datetime.datetime.now(UTC) + datetime.timedelta(minutes=minutes)).astimezone(zone).replace(microsecond=0).isoformat()


def fresh(client) -> int:
    """A new deployment of seq_wf: deployments of a project run one after the other"""
    from test_web_deployment import cancel_open_deployments
    cancel_open_deployments(client, 'seq')
    return client.create_deployment('seq_wf')


def schedule(client, deployment: int, stage: str='START', run_at: str|None=None, option: str='continue') -> tuple[int, dict]:
    stage_id = client.get_stages(deployment)[stage]['id']
    return client.post_json(f"/api/run_stage/{deployment}/{stage_id}/{option}", {'run_at': run_at or in_minutes(60)})


def jobs(client, deployment: int) -> list[dict]:
    return client.get_deployment(deployment)['processing_jobs']


def history(client, deployment: int, action: str) -> list[dict]:
    rows = json.loads(client.get(f"/api/show_processing_history/{deployment}")[2])
    return [row for row in rows if row['action'] == action]


def page_of(client, deployment: int) -> str:
    status, _, text = client.get(f"/show_details/{deployment}", headers=HTML)
    assert status == 200, text[:300]
    return text


def text_of(markup: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', markup))).strip()


def attention(page: str) -> tuple|None:
    """(kind, text, actions of its buttons)"""
    found = re.search(r'<section class="ir-attention k-(\w+)".*?<p class="ir-attention-text">(.*?)</p>(.*?)</section>', page, re.S)
    if not found:
        return None
    return found.group(1), text_of(found.group(2)), re.findall(r'data-action="([^"]+)"', found.group(3))


def utc_text(iso: str) -> str:
    return datetime.datetime.fromisoformat(iso).astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')


def execute(server, sql: str, params: tuple=()) -> None:
    """Changes the database of the web app, as if time had passed or the service had done something"""
    with sqlite3.connect(server.path('var', 'app.sqlite'), timeout=30) as conn:
        conn.execute(sql, params)
    conn.close()



def test_schedule_a_stage(boss):

    deployment = fresh(boss)
    run_at = in_minutes(90, offset_hours=1)

    status, result = schedule(boss, deployment, run_at=run_at)

    assert status == 200, result
    assert result['mode'] == 'service' and result['service_running'] is False
    stored = datetime.datetime.fromisoformat(result['run_at'])
    assert stored == datetime.datetime.fromisoformat(run_at) and stored.utcoffset() == datetime.timedelta(0)

    [job] = jobs(boss, deployment)
    assert (job['id'], job['status'], job['user'], job['run_at']) == (result['job_id'], 'queued', 'BOSS', result['run_at'])

    # The stage isn't touched until its time
    assert boss.get_stages(deployment)['START']['status'] == 'ready'

    [entry] = history(boss, deployment, 'schedule_stage')
    assert (entry['user'], entry['stage']) == ('BOSS', 'START')
    assert utc_text(run_at) in entry['details']

    boss.post(f"/api/cancel_deployment/{deployment}")
    assert jobs(boss, deployment) == []



@pytest.mark.parametrize('run_at, message', [
    (lambda: in_minutes(-5), 'in the past'),
    (lambda: in_minutes(60).rsplit('+', 1)[0], 'time zone offset'),
    (lambda: 'tonight', 'not a valid date'),
    (lambda: 1764000000, 'needs to be'),
])
def test_invalid_time(boss, run_at, message):

    deployment = fresh(boss)
    stage_id = boss.get_stages(deployment)['START']['id']

    status, result = boss.post_json(f"/api/run_stage/{deployment}/{stage_id}/continue", {'run_at': run_at()})

    assert status == 422 and message in result['message'], result
    assert jobs(boss, deployment) == []
    boss.post(f"/api/cancel_deployment/{deployment}")



def test_deployment_is_blocked_while_a_run_is_scheduled(boss):

    deployment = fresh(boss)
    assert schedule(boss, deployment)[0] == 200

    # Not run now, not scheduled twice
    assert boss.run_stage(deployment, 'START')[0] == 409
    assert schedule(boss, deployment, run_at=in_minutes(10))[0] == 409

    # The mode can't be switched while it waits in the queue
    status, result = boss.post_json('/api/set_processing_mode/thread')
    assert status == 409, result

    boss.post(f"/api/cancel_deployment/{deployment}")



def test_permissions(server, boss):

    deployment = fresh(boss)
    stranger = server.client('stranger')
    runner = server.client('runner')

    # read only
    assert schedule(stranger, deployment)[0] == 403
    assert jobs(boss, deployment) == []

    status, result = schedule(boss, deployment)
    assert status == 200

    assert stranger.post(f"/api/cancel_job/{result['job_id']}")[0] == 403

    # Another user with `run` may cancel it
    assert runner.post(f"/api/cancel_job/{result['job_id']}")[0] == 200
    assert jobs(boss, deployment) == []
    assert boss.get_stages(deployment)['START']['status'] == 'ready'

    [entry] = history(boss, deployment, 'cancel_schedule')
    assert (entry['user'], entry['stage']) == ('RUNNER', 'START')
    assert f"job {result['job_id']}" in entry['details']

    # Canceled already
    assert runner.post(f"/api/cancel_job/{result['job_id']}")[0] == 409

    # Scheduled again by the runner
    assert schedule(runner, deployment)[0] == 200
    boss.post(f"/api/cancel_deployment/{deployment}")



def test_running_job_can_not_be_canceled(server, boss):

    deployment = fresh(boss)
    status, result = schedule(boss, deployment)
    assert status == 200

    # The service has taken it
    execute(server, "UPDATE processing_jobs SET status = 'running' WHERE id = ?", (result['job_id'],))

    status, answer = boss.post_json(f"/api/cancel_job/{result['job_id']}")
    assert status == 409, answer
    assert jobs(boss, deployment)[0]['status'] == 'running'

    execute(server, "UPDATE processing_jobs SET status = 'canceled' WHERE id = ?", (result['job_id'],))
    boss.post(f"/api/cancel_deployment/{deployment}")



def test_page_of_a_scheduled_stage(boss):

    deployment = fresh(boss)
    start_id = boss.get_stages(deployment)['START']['id']

    # Ready: Run and Run at…
    kind, text, actions = attention(page_of(boss, deployment))
    assert (kind, actions) == ('ready', ['run-stage', 'schedule-stage'])
    panel = boss.get(f"/show_details/{deployment}/stage/{start_id}", headers=HTML)[2]
    assert 'data-action="run-stage"' in panel and 'data-action="schedule-stage"' in panel

    status, result = schedule(boss, deployment)
    assert status == 200

    page = page_of(boss, deployment)
    kind, text, actions = attention(page)
    assert kind == 'queued'
    assert text == f"Stage START runs at {utc_text(result['run_at'])}, scheduled by BOSS. The processing service is not running."
    assert actions == ['cancel-schedule']
    assert f'<time datetime="{result["run_at"]}" data-local-time>' in page
    assert f'data-job-id="{result["job_id"]}"' in page

    # The flow shows it as scheduled
    assert re.search(r'data-stage-id="%d" data-state="scheduled"' % start_id, page)

    panel = boss.get(f"/show_details/{deployment}/stage/{start_id}", headers=HTML)[2]
    schedule_line = text_of(re.search(r'<p class="ir-steps-schedule">(.*?)</p>', panel, re.S).group(1))
    assert schedule_line == f"Runs at {utc_text(result['run_at'])} (continue), scheduled by BOSS"
    assert 'data-action="cancel-schedule"' in panel
    assert 'data-action="run-stage"' not in panel and 'data-action="schedule-stage"' not in panel

    boss.post(f"/api/cancel_deployment/{deployment}")



def test_page_after_a_scheduled_run_which_did_not_start(server, boss):

    deployment = fresh(boss)
    start_id = boss.get_stages(deployment)['START']['id']
    run_at = (datetime.datetime.now(UTC) - datetime.timedelta(hours=3)).replace(microsecond=0).isoformat()
    error = 'Missed the scheduled time by 120 minutes (limit C_SCHEDULE_MAX_DELAY_MINUTES = 60), e.g. because the processing service wasn\'t running. The stage has not been run.'

    # Like the job process of the service
    execute(server, """INSERT INTO processing_jobs (meta_file_id, stage_id, continue_run, user, status, error, create_time, start_time, end_time, run_at)
                       VALUES (?, ?, 1, 'BOSS', 'failed', ?, ?, ?, ?, ?)""",
            (deployment, start_id, error, *[datetime.datetime.now().isoformat()] * 3, run_at))

    page = page_of(boss, deployment)
    kind, text, actions = attention(page)
    assert kind == 'danger'
    assert text == f"The scheduled run of START at {utc_text(run_at)} did not start. {error}"
    assert actions == ['run-stage', 'schedule-stage']

    panel = boss.get(f"/show_details/{deployment}/stage/{start_id}", headers=HTML)[2]
    assert 'class="ir-steps-schedule k-danger"' in panel

    # A new schedule replaces the notice
    assert schedule(boss, deployment)[0] == 200
    assert attention(page_of(boss, deployment))[0] == 'queued'

    boss.post(f"/api/cancel_deployment/{deployment}")



def test_jobs_on_the_settings_page(boss):

    deployment = fresh(boss)
    status, result = schedule(boss, deployment)
    assert status == 200

    text = boss.get('/settings/processing', headers=HTML)[2]
    rows = json.loads(html.unescape(re.search(r'id="jobs-data">(.*?)</script>', text, re.S).group(1)))
    [row] = [row for row in rows if row['id'] == result['job_id']]
    assert row['scheduled'] == result['run_at']
    assert (row['status'], row['status_view']['text']) == ('queued', 'scheduled')

    boss.post(f"/api/cancel_deployment/{deployment}")



def test_only_with_the_processing_service(boss):

    deployment = fresh(boss)
    assert boss.post_json('/api/set_processing_mode/thread')[0] == 200

    try:
        status, result = schedule(boss, deployment)
        assert status == 409 and "mode 'service'" in result['message'], result
        assert jobs(boss, deployment) == []

        # No Run at…
        kind, text, actions = attention(page_of(boss, deployment))
        assert actions == ['run-stage']
        start_id = boss.get_stages(deployment)['START']['id']
        assert 'schedule-stage' not in boss.get(f"/show_details/{deployment}/stage/{start_id}", headers=HTML)[2]
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")
        assert boss.post_json('/api/set_processing_mode/service')[0] == 200



#---------------------------------------------------------
# With the processing service
#---------------------------------------------------------

@pytest.fixture(scope='module')
def service_server():

    s = Web_Server(settings="C_PROCESSING_MODE = 'service'\nC_SERVICE_POLL_INTERVAL = 0.5\n").start()
    service = subprocess.Popen([sys.executable, os.path.join(s.directory, 'serviceapp', 'service.py')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    s.wait_for_service()

    yield s

    service.terminate()
    service.wait(timeout=10)
    s.close()



def test_service_runs_the_stage_at_its_time(service_server):

    client = service_server.client('boss')
    deployment = fresh(client)

    # In the time zone of a user in Tokyo
    run_at = (datetime.datetime.now(UTC) + datetime.timedelta(seconds=4)).astimezone(datetime.timezone(datetime.timedelta(hours=9))).isoformat()
    status, result = schedule(client, deployment, run_at=run_at)
    assert status == 200 and result['service_running'] is True

    time.sleep(1)
    assert client.get_stages(deployment)['START']['status'] == 'ready'
    assert jobs(client, deployment)[0]['status'] == 'queued'

    stage = client.wait_for_stage(deployment, 'START', timeout=30)
    assert stage['status'] == 'finished'

    [run] = history(client, deployment, 'run_stage')
    assert run['user'] == 'BOSS'
    assert run['details'] == f"Scheduled run for {utc_text(result['run_at'])} (job {result['job_id']})"
    # Not before its time
    assert datetime.datetime.fromisoformat(run['timestamp']).astimezone(UTC) >= datetime.datetime.fromisoformat(result['run_at'])

    client.post(f"/api/cancel_deployment/{deployment}")
