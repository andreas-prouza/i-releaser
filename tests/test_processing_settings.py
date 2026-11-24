"""Processing mode and processing service in the web app (docs/features/processing-settings-in-web-app.md)"""
import json, os, time

import pytest

from web_server import Web_Server, is_running



@pytest.fixture
def server():
    s = Web_Server().start()
    yield s
    s.close()



def test_next_stage_runs_in_the_new_mode(server):

    boss = server.client('boss')

    status, data = boss.run_stage(boss.create_deployment('hidden_wf'), 'START')
    assert (status, data['mode']) == (200, 'thread')

    status, data = boss.post_json('/api/set_processing_mode/service')
    assert (status, data['mode'], data['service_running']) == (200, 'service', False)

    with open(server.path('etc', 'app.json')) as f:
        assert json.load(f) == {'C_PROCESSING_MODE': 'service'}

    status, data = boss.run_stage(boss.create_deployment('seq_wf'), 'START')
    assert (status, data['mode'], data['service_running']) == (200, 'service', False)
    job_id = data['job_id']

    # The stage waits in the queue of the service
    status, data = boss.post_json('/api/set_processing_mode/thread')
    assert status == 409, data
    assert 'waiting in the queue' in data['message']

    assert boss.post_json(f'/api/cancel_job/{job_id}')[0] == 200
    assert boss.post_json('/api/set_processing_mode/thread')[0] == 200

    status, data = boss.run_stage(boss.create_deployment('slow_wf'), 'START')
    assert (status, data['mode']) == (200, 'thread')

    assert "Processing mode changed from 'service' to 'thread' by BOSS" in server.read_logs()



def test_settings_page_shows_the_mode_and_its_source(server):

    boss = server.client('boss')

    status, _, text = boss.get('/settings/processing', headers={'Accept': 'text/html'})
    assert status == 200
    assert '<option value="thread" selected>' in text
    assert 'from default' in text

    # A page of its own (docs/features/web-ui-admin-pages.md#settings)
    assert '<a class="nav-link active" href="/settings/processing" aria-current="page">Processing</a>' in text

    boss.post_json('/api/set_processing_mode/service')

    _, _, text = boss.get('/settings/processing', headers={'Accept': 'text/html'})
    assert '<option value="service" selected>' in text
    assert 'from web app' in text



def test_mode_from_the_settings_file():

    server = Web_Server(settings="C_PROCESSING_MODE = 'service'\n").start()
    try:
        _, _, text = server.client('boss').get('/settings/processing', headers={'Accept': 'text/html'})
        assert '<option value="service" selected>' in text
        assert 'from etc/settings.py' in text
    finally:
        server.close()



@pytest.mark.parametrize('path', ['/api/set_processing_mode/service', '/api/processing_service/start', '/api/set_service_auto_start/true'])
def test_only_for_admins(server, path):

    for user in ['intern', 'stranger', 'runner']:
        status, data = server.client(user).post_json(path)
        assert status == 403, (user, data)

    assert not os.path.exists(server.path('etc', 'app.json'))
    assert server.get_service_pid() is None



@pytest.mark.parametrize('path', ['/api/set_processing_mode/service', '/api/processing_service/start', '/api/set_service_auto_start/true'])
def test_actions_need_post(server, path):

    boss = server.client('boss')

    assert boss.get(path)[0] == 405

    boss.origin = 'https://evil.example'
    assert boss.post(path)[0] == 403

    assert not os.path.exists(server.path('etc', 'app.json'))
    assert server.get_service_pid() is None



@pytest.mark.parametrize('path', ['/api/set_processing_mode/fast', '/api/processing_service/kill', '/api/set_service_auto_start/maybe'])
def test_invalid_input(server, path):
    assert server.client('boss').post_json(path)[0] == 422



def test_service_started_by_the_web_app_keeps_running(server):

    boss = server.client('boss')

    status, data = boss.post_json('/api/processing_service/start')
    assert status == 200, data
    assert data['service_running'], data['output']
    assert 'Service is running' in data['output']
    assert '\x1b' not in data['output']

    pid = server.get_service_pid()
    assert pid is not None and is_running(pid)

    server.stop()
    # A time has to pass: the service keeps running after the web app has ended
    time.sleep(0.5)
    assert is_running(pid)

    # And it can be stopped by the web app
    server.start()
    boss = server.client('boss')
    status, data = boss.post_json('/api/processing_service/stop')
    assert status == 200, data
    assert not data['service_running']
    assert not is_running(pid)



def test_restart_of_the_service(server):

    boss = server.client('boss')
    boss.post_json('/api/processing_service/start')
    old_pid = server.get_service_pid()

    status, data = boss.post_json('/api/processing_service/restart')
    assert (status, data['service_running']) == (200, True), data
    assert server.get_service_pid() not in (None, old_pid)



def test_settings_page_without_settings_file():

    server = Web_Server()
    os.remove(os.path.join(server.directory, 'etc', 'settings.py'))
    server.start()
    try:
        status, _, text = server.client('boss').get('/settings/processing', headers={'Accept': 'text/html'})
        assert status == 200, text
        assert 'from default' in text
    finally:
        server.close()
