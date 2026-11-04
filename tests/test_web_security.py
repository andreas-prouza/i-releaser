"""Security of the web app, tested against the running application"""
import json, os, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

import pytest

from web_server import Web_Server


@pytest.fixture(scope='module')
def server():
    s = Web_Server().start()
    yield s
    s.close()



#---------------------------------------------------------
# current-user-shared-between-requests
#---------------------------------------------------------

def test_user_never_gets_permissions_of_another_user(server):

    boss, intern = server.client('boss'), server.client('intern')

    def boss_request(_):
        return boss.get('/api/get_workflows')[0]

    def intern_request(_):
        return intern.get('/settings')[0]

    with ThreadPoolExecutor(30) as pool:
        boss_results = pool.map(boss_request, range(300))
        intern_results = list(pool.map(intern_request, range(300)))

    assert set(boss_results) == {200}
    assert set(intern_results) == {403}



def test_stage_is_recorded_with_the_user_who_started_it(server):

    boss, intern = server.client('boss'), server.client('intern')
    deployment = boss.create_deployment('slow_wf')

    assert boss.run_stage(deployment, 'START')[0] == 200

    # Another user is using the web app while the stage is running
    for _ in range(20):
        intern.get('/api/get_workflows')

    boss.wait_for_stage(deployment, 'START')

    history = json.loads(boss.get(f"/api/show_processing_history/{deployment}")[2])
    assert {row['user'] for row in history} == {'BOSS'}



#---------------------------------------------------------
# session-takeover-via-logs
#---------------------------------------------------------

def test_session_id_changes_at_the_login(server):

    client = server.client()
    client.login('nobody')
    assert client.session_id is not None
    before = list(client.sent_session_ids)

    assert client.login('boss') == 200
    assert client.session_id not in before
    assert client.get('/settings')[0] == 200



def test_no_session_id_in_the_logs(server):

    client = server.client()
    client.login('nobody')
    client.login('boss')
    client.get('/')

    logs = server.read_logs()

    for session_id in client.sent_session_ids:
        assert session_id not in logs



def test_logs_are_only_for_admins(server):

    intern, boss = server.client('intern'), server.client('boss')
    log_name = os.listdir(os.path.join(server.web_dir, 'log'))[0]

    assert intern.get(f"/log/{log_name}/10")[0] == 403
    assert '/log/' not in intern.get('/', headers={'Accept': 'text/html'})[2]

    assert boss.get(f"/log/{log_name}/10", headers={'Accept': 'text/html'})[0] == 200
    assert '/log/' in boss.get('/', headers={'Accept': 'text/html'})[2]

    assert boss.get("/log/does-not-exist/10")[0] == 404



def test_logout_ends_the_session(server):

    client = server.client('boss')
    session_id = client.session_id

    client.get('/logout')

    other = server.client()
    other.session_id = session_id
    assert other.get('/api/get_workflows')[0] == 401



#---------------------------------------------------------
# api-token-stored-in-custom-data
#---------------------------------------------------------

def get_token(client) -> str:
    return client.post_json('/api/generate_user_key')[1]['token']



def test_token_is_not_stored_and_not_logged(server):

    token = get_token(server.client('boss'))
    client = server.client()

    status, _, text = client.get(f"/api/start_workflow/hidden_wf?auth-token={token}&a=1")

    assert status == 200
    assert json.loads(text)['meta_file']['custom_data'] == {'a': '1'}
    assert token not in server.read_logs()



def test_token_in_the_header(server):

    boss = server.client('boss')
    token = get_token(boss)
    client = server.client()

    assert client.get('/api/get_projects', headers={'Authorization': f"Bearer {token}"})[0] == 200
    assert client.get('/api/get_projects', headers={'Authorization': 'Bearer wrong'})[0] == 401
    assert client.session_id is None



def test_token_requests_leave_no_session_files(server):

    token = get_token(server.client('boss'))
    sessions = os.path.join(server.web_dir, 'sessions')
    before = len(os.listdir(sessions))

    for _ in range(5):
        server.client().get('/api/get_projects', headers={'Authorization': f"Bearer {token}"})

    assert len(os.listdir(sessions)) == before



#---------------------------------------------------------
# weak-api-tokens
#---------------------------------------------------------

def test_new_token_is_strong_and_stored_once(server):

    boss = server.client('boss')
    tokens = {get_token(boss) for _ in range(3)}

    assert len(tokens) == 3
    assert all(len(token) >= 43 for token in tokens)

    with open(os.path.join(server.web_dir, 'etc', 'keys.json')) as f:
        keys = json.load(f)

    assert keys['boss']['key'] not in tokens



def test_old_tokens_stay_valid(server):

    import hashlib

    old_token = hashlib.sha256(b'abcdefghij').hexdigest()
    path = os.path.join(server.web_dir, 'etc', 'keys.json')

    with open(path) as f:
        keys = json.load(f)

    keys['intern'] = {'key': hashlib.sha256(old_token.encode()).hexdigest(), 'orig_key_masked': '', 'date': ''}

    with open(path, 'w') as f:
        json.dump(keys, f)

    assert server.client().get('/api/get_projects', headers={'Authorization': f"Bearer {old_token}"})[0] == 200



def test_last_use_of_a_token_is_shown(server):

    boss = server.client('boss')
    token = get_token(boss)

    server.client().get('/api/get_projects', headers={'Authorization': f"Bearer {token}"})

    assert re.search(r'Last used</th><td><code>\d{4}-', boss.get('/user', headers={'Accept': 'text/html'})[2])



#---------------------------------------------------------
# cors-allows-any-origin
#---------------------------------------------------------

def test_no_cors_headers_by_default(server):

    boss = server.client('boss')

    _, headers, _ = boss.get('/api/get_projects', headers={'Origin': 'https://evil.example'})
    assert 'access-control-allow-origin' not in headers

    _, headers, _ = boss.request('OPTIONS', '/api/edit_custom_data/1', headers={'Origin': 'https://evil.example', 'Access-Control-Request-Method': 'POST'})
    assert 'access-control-allow-origin' not in headers



def test_configured_origin_gets_cors_headers():

    server = Web_Server(env={'X': '1'})

    with open(os.path.join(server.web_dir, 'etc', 'global_cfg.py'), 'a') as f:
        f.write("\nC_CORS_ALLOWED_ORIGINS = ['https://allowed.example']\n")

    try:
        server.start()
        boss = server.client('boss')

        assert boss.get('/api/get_projects', headers={'Origin': 'https://allowed.example'})[1].get('access-control-allow-origin') == 'https://allowed.example'
        assert 'access-control-allow-origin' not in boss.get('/api/get_projects', headers={'Origin': 'https://evil.example'})[1]

    finally:
        server.close()



#---------------------------------------------------------
# csrf-actions-via-get
#---------------------------------------------------------

ACTIONS = [
    '/api/run_stage/1/1/continue',
    '/api/cancel_deployment/1',
    '/api/cancel_job/1',
    '/api/reset_stage_status/1/1',
    '/api/reset_last_finished_stage/1/1',
    '/api/reset_deployment_status/1',
    '/api/set_check_error/1/1/1/false',
    '/api/create_deployment/hidden_wf',
    '/api/start_workflow/hidden_wf',
]


@pytest.mark.parametrize('path', ACTIONS)
def test_no_action_with_get_and_session(server, path):
    assert server.client('boss').get(path)[0] == 405



def test_get_with_a_session_changes_nothing(server):

    boss = server.client('boss')
    deployment = boss.create_deployment('hidden_wf')

    assert boss.get(f"/api/cancel_deployment/{deployment}")[0] == 405
    assert boss.get_deployment(deployment)['general']['status'] == 'ready'



def test_post_from_another_origin_is_rejected(server):

    boss = server.client('boss')
    deployment = boss.create_deployment('hidden_wf')

    boss.origin = 'https://evil.example'
    assert boss.post(f"/api/cancel_deployment/{deployment}")[0] == 403

    boss.origin = None
    assert boss.post(f"/api/cancel_deployment/{deployment}")[0] == 403

    boss.origin = f"http://127.0.0.1:{server.port}"
    assert boss.get_deployment(deployment)['general']['status'] == 'ready'
    assert boss.post(f"/api/cancel_deployment/{deployment}")[0] == 200



def test_api_token_keeps_working_with_get(server):

    token = get_token(server.client('boss'))
    client = server.client()

    status, _, text = client.get('/api/create_deployment/hidden_wf', headers={'Authorization': f"Bearer {token}"})
    assert status == 200

    deployment = json.loads(text)['meta_file']['general']['id']
    assert client.get(f"/api/cancel_deployment/{deployment}", headers={'Authorization': f"Bearer {token}"})[0] == 200



#---------------------------------------------------------
# session-store-hardening
#---------------------------------------------------------

@pytest.mark.parametrize('cookie', ['../../etc/user_permissions', 'abc', '../sessions/x'])
def test_invalid_session_id_is_no_session(server, cookie):

    client = server.client()
    client.session_id = cookie

    assert client.get('/api/get_projects')[0] == 401



def test_cookie_flags(server):

    client = server.client()
    _, headers, _ = client.request('POST', '/', form={'user': 'nobody', 'password': 'x'}, headers={'Accept': 'text/html'})

    cookie = headers['set-cookie'].lower()
    assert 'httponly' in cookie
    assert 'samesite=lax' in cookie
    assert 'secure' not in cookie



def test_secure_cookie_with_the_setting():

    server = Web_Server()

    with open(os.path.join(server.web_dir, 'etc', 'global_cfg.py'), 'a') as f:
        f.write("\nC_COOKIE_SECURE = True\n")

    try:
        server.start()
        _, headers, _ = server.client().request('POST', '/', form={'user': 'nobody', 'password': 'x'}, headers={'Accept': 'text/html'})
        assert 'secure' in headers['set-cookie'].lower()
    finally:
        server.close()



#---------------------------------------------------------
# local-debugging-mode-without-password
#---------------------------------------------------------

def test_warning_and_banner_in_local_debugging_mode(server):

    assert 'password check of the login is turned off' in server.read_logs()
    assert 'password check of the login is turned off' in server.client('boss').get('/', headers={'Accept': 'text/html'})[2]



def test_index_does_not_turn_off_the_password_check():

    with open(os.path.join(os.path.dirname(__file__), '..', 'webapp', 'index.py')) as f:
        assert 'os.environ["I_RELEASER_LOCAL_DEBUGGING"]' not in f.read()



def test_local_debugging_is_refused_under_gunicorn():

    server = Web_Server()

    try:
        with open(os.path.join(server.web_dir, 'etc', 'gunicorn.conf.py'), 'w') as f:
            f.write(f"bind = '127.0.0.1:{server.port}'\nworkers = 1\nworker_class = 'uvicorn.workers.UvicornWorker'\n")

        result = subprocess.run([sys.executable, '-m', 'gunicorn', '--config=etc/gunicorn.conf.py', 'wsgi:app'], cwd=server.web_dir, env=server.get_environment(), capture_output=True, text=True, timeout=30)

        assert result.returncode != 0
        assert 'must not be set on a server' in result.stdout + result.stderr

    finally:
        server.close()



#---------------------------------------------------------
# login-connection-string-injection
#---------------------------------------------------------

def test_failed_logins_are_blocked():

    server = Web_Server(settings="C_LOGIN_MAX_FAILURES = 3\n").start()

    try:
        client = server.client()

        for _ in range(3):
            client.login('nobody')

        status, _, text = client.request('POST', '/', form={'user': 'nobody', 'password': 'x'}, headers={'Accept': 'text/html'})
        assert 'Too many failed logins' in text

        # Also with a correct login from this client
        status, _, text = client.request('POST', '/', form={'user': 'boss', 'password': 'x'}, headers={'Accept': 'text/html'})
        assert 'Too many failed logins' in text

    finally:
        server.close()
