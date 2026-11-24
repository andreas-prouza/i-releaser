"""Defects of the code review of 2026-11-23 (docs/bugfixes/README.md#review-of-2026-11-23), tested against the running web app"""
import http.client, json, os, sqlite3, threading, time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import pytest

from web_server import Web_Server, wait_until


@pytest.fixture(scope='module')
def server():
    s = Web_Server().start()
    yield s
    s.close()


@pytest.fixture()
def boss(server):
    return server.client('boss')


def cancel_open_deployments(client, project: str) -> None:
    """Deployments of a project run one after the other"""

    for deployment in json.loads(client.get(f"/api/list_deployments/{project}")[2]):
        if deployment['status'] not in ['finished', 'canceled']:
            client.post(f"/api/cancel_deployment/{deployment['meta_file_id']}")


def history_actions(server, deployment: int) -> list[str]:

    with sqlite3.connect(server.path('var', 'app.sqlite')) as conn:
        return [row[0] for row in conn.execute("SELECT action FROM processing_users WHERE meta_file_id = ? ORDER BY id", (deployment,))]



#---------------------------------------------------------
# cancel-finished-deployment
#---------------------------------------------------------

def test_finished_deployment_can_not_be_canceled(server, boss):

    cancel_open_deployments(boss, 'seq')
    deployment = boss.create_deployment('seq_wf')
    boss.finish_deployment(deployment)
    assert boss.get_deployment(deployment)['general']['status'] == 'finished'
    history = history_actions(server, deployment)

    status, body = boss.post_json(f"/api/cancel_deployment/{deployment}")

    assert status == 409
    assert 'finished' in body['message']
    assert boss.get_deployment(deployment)['general']['status'] == 'finished'
    # A cancel which didn't happen isn't in the history
    assert history_actions(server, deployment) == history


def test_canceled_deployment_can_not_be_canceled_again(server, boss):

    cancel_open_deployments(boss, 'seq')
    deployment = boss.create_deployment('seq_wf')

    assert boss.post_json(f"/api/cancel_deployment/{deployment}")[0] == 200
    assert history_actions(server, deployment).count('cancel_workflow') == 1

    assert boss.post_json(f"/api/cancel_deployment/{deployment}")[0] == 409
    assert history_actions(server, deployment).count('cancel_workflow') == 1
    assert boss.get_deployment(deployment)['general']['status'] == 'canceled'



#---------------------------------------------------------
# minor-web-defects-2026-11, item 10
#---------------------------------------------------------

@pytest.mark.parametrize('body', [
    {'lib': 'devlib', 'name': 'orders', 'checked': False},
    {'lib': 'devlib', 'name': 'orders', 'type': 'file', 'checked': 'false'},
    {'lib': 'devlib', 'name': 'orders', 'type': 'file'},
])
def test_set_source_ready_checks_its_input(boss, body):

    cancel_open_deployments(boss, 'seq')
    deployment = boss.create_deployment('seq_wf')

    status, answer = boss.post_json(f"/api/set_source_ready_4_deployment/{deployment}", body)

    assert status == 422, answer



#---------------------------------------------------------
# logout-undone-by-concurrent-request
#---------------------------------------------------------

SLOW_ROUTE = '''
import asyncio, os
from fastapi import Request
from index import app

async def slow_change(request: Request):
    # The test waits for it: the request has started
    open(os.path.join(os.environ['I_RELEASER_WEBAPP_PATH'], 'slow_started'), 'w').close()
    await asyncio.sleep(1.5)
    request.state.session['changed'] = True
    return {}

app.add_api_route('/test_slow_change', slow_change, methods=['GET'])
'''


@pytest.fixture(scope='module')
def session_server():
    s = Web_Server()
    with open(os.path.join(s.web_dir, 'custom', 'routes', 'review_slow_route.py'), 'w') as f:
        f.write(SLOW_ROUTE)
    s.start()
    yield s
    s.close()


def session_files(server) -> list[str]:
    return os.listdir(os.path.join(server.web_dir, 'sessions'))


def session_file(server, client) -> str:
    return os.path.join(server.web_dir, 'sessions', f"{client.session_id}.json")


def test_request_during_logout_does_not_restore_the_session(session_server):

    client = session_server.client('boss')
    assert client.get('/workflows')[0] == 200

    marker = os.path.join(session_server.web_dir, 'slow_started')
    slow = threading.Thread(target=lambda: client.get('/test_slow_change'))
    slow.start()
    wait_until(lambda: os.path.exists(marker), what='the slow request has started')

    assert client.post('/logout')[0] in [302, 303]
    slow.join()

    assert not os.path.exists(session_file(session_server, client))
    assert client.get('/workflows')[0] == 401


def test_failed_logins_create_no_session_file(session_server):

    before = session_files(session_server)

    # Fewer than C_LOGIN_CLIENT_MAX_FAILURES: the other tests of the module log in from the same address
    for _ in range(9):
        session_server.client().login('nobody', 'wrong')

    assert session_files(session_server) == before


def test_reading_does_not_write_the_session(session_server):

    client = session_server.client('boss')
    modified = os.path.getmtime(session_file(session_server, client))
    # A time has to pass: a write afterwards would change the time of the file
    time.sleep(0.05)

    assert client.get('/workflows')[0] == 200
    assert os.path.getmtime(session_file(session_server, client)) == modified


def test_background_requests_do_not_extend_the_session(session_server):

    client = session_server.client('boss')
    path = session_file(session_server, client)

    with open(path) as f:
        data = json.load(f)
    data['last-update'] = (datetime.now() - timedelta(minutes=30)).isoformat()
    with open(path, 'w') as f:
        json.dump(data, f)

    assert client.get('/workflows', headers={'X-Background': '1'})[0] == 200
    with open(path) as f:
        assert json.load(f)['last-update'] == data['last-update']

    assert client.get('/workflows')[0] == 200
    with open(path) as f:
        assert json.load(f)['last-update'] != data['last-update']


def test_session_cookie_ends_with_the_browser(session_server):

    client = session_server.client()
    connection = http.client.HTTPConnection('127.0.0.1', session_server.port, timeout=30)
    try:
        connection.request('POST', '/login', body=urlencode({'user': 'boss', 'password': 'x'}),
                           headers={'Content-Type': 'application/x-www-form-urlencoded', 'Origin': client.origin})
        response = connection.getresponse()
        cookies = [value for key, value in response.getheaders() if key.lower() == 'set-cookie']
    finally:
        connection.close()

    assert len(cookies) == 1
    assert 'max-age' not in cookies[0].lower()



#---------------------------------------------------------
# api-token-outlives-user
#---------------------------------------------------------

def keys_file(server) -> str:
    return os.path.join(server.web_dir, 'etc', 'keys.json')


def tokens_of(server, user: str) -> list[dict]:
    """The rows of the user in the table api_tokens (docs/features/api-v2.md#tokens)"""
    with sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite')) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT * FROM api_tokens WHERE user = ?", (user,))]


def token_client(server, token: str):
    client = server.client()
    client.headers['Authorization'] = f"Bearer {token}"
    return client


def new_token(server, user: str) -> str:
    status, data = server.client(user).post_json('/api/generate_user_key')
    assert status == 200, data
    return data['token']


def test_token_of_a_removed_user_is_deleted(server, boss):

    token = new_token(server, 'intern')
    assert token_client(server, token).get('/api/get_workflows')[0] == 200

    status, body = boss.post_json('/api/save_permissions', {'deleted_users': ['intern']})
    assert status == 200, body
    assert tokens_of(server, 'intern') == []

    # The same name again: the old token doesn't work
    status, body = boss.post_json('/api/add_permission', {'type': 'user', 'name': 'intern', 'general': ['read', 'start workflow']})
    assert status == 200, body
    assert token_client(server, token).get('/api/get_workflows')[0] == 401


def test_admin_revokes_a_token(server, boss):

    token = new_token(server, 'runner')

    assert server.client('runner').post('/api/revoke_token/runner')[0] == 403
    assert boss.post('/api/revoke_token/runner')[0] == 200
    assert boss.post('/api/revoke_token/runner')[0] == 404
    assert token_client(server, token).get('/api/get_workflows')[0] == 401


def test_expired_token(server, boss):

    token = new_token(server, 'runner')
    assert tokens_of(server, 'runner')[0]['expires_at'] > datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite')) as conn:
        conn.execute("UPDATE api_tokens SET expires_at = ? WHERE user = 'runner'", ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec='seconds'),))

    status, _, text = token_client(server, token).get('/api/get_workflows')
    assert status == 401
    assert 'expired' in text


def test_token_of_the_old_format_is_accepted_with_a_warning(server, boss):

    import hashlib
    old_token = hashlib.sha256(b'abcdefghij').hexdigest()
    server.client('boss').post('/api/revoke_token/runner')
    # The store before 2026-11 (e.g. restored from a backup): taken over into the database when it appears
    with open(keys_file(server), 'w') as f:
        json.dump({'runner': {'key': hashlib.sha256(old_token.encode()).hexdigest(), 'orig_key_masked': '*****xyz', 'date': '2025-01-01 10:00:00'}}, f)

    assert token_client(server, old_token).get('/api/get_workflows')[0] == 200
    assert not os.path.exists(keys_file(server)) and os.path.exists(keys_file(server) + '.migrated')

    token = tokens_of(server, 'runner')[0]
    assert token['legacy'] == 1 and token['name'] == 'API token' and token['scope'] == 'write'
    # Expires C_TOKEN_MAX_DAYS after its first use with this version
    assert token['expires_at'] > (datetime.now(timezone.utc) + timedelta(days=300)).isoformat()

    _, _, page = server.client('runner').get('/user', headers={'Accept': 'text/html'})
    assert 'old format' in page



#---------------------------------------------------------
# minor-web-defects-2026-11, items 4, 6, 8, 9
#---------------------------------------------------------

@pytest.fixture(scope='module')
def web_server():
    s = Web_Server(settings="C_WATCH_SESSION_CHECK_SECONDS = 1\n")
    with open(os.path.join(s.web_dir, 'custom', 'routes', 'review_broken_route.py'), 'w') as f:
        f.write("this is not python\n")
    s.start()
    yield s
    s.close()


def test_pages_are_not_cached(web_server):

    client = web_server.client('boss')

    assert client.get('/workflows', headers={'Accept': 'text/html'})[1]['cache-control'] == 'no-store'
    assert client.get('/api/get_workflows')[1]['cache-control'] == 'no-store'
    assert client.get('/static/assets/css/app.css')[1]['cache-control'] == 'max-age=0'


def test_broken_custom_route_does_not_stop_the_web_app(web_server):

    status, _, page = web_server.client('boss').get('/settings', headers={'Accept': 'text/html'})

    assert status == 200
    assert 'review_broken_route.py' in page


@pytest.mark.parametrize('method, path, status', [('GET', '/api/does_not_exist', 404), ('GET', '/api/generate_user_key', 405), ('GET', '/show_details/abc', 422)])
def test_errors_of_fastapi_have_the_error_format(web_server, method, path, status):

    answer_status, _, text = web_server.client('boss').request(method, path)

    assert answer_status == status
    body = json.loads(text)
    assert body['status'] == 'error' and isinstance(body['message'], str)


def test_live_updates_end_after_the_logout(web_server):

    client = web_server.client('boss')
    deployment = client.create_deployment('hidden_wf')

    connection = http.client.HTTPConnection('127.0.0.1', web_server.port, timeout=10)
    connection.request('GET', f"/api/watch_state/{deployment}", headers={'Cookie': f"session_id={client.session_id}"})
    response = connection.getresponse()
    assert response.status == 200
    response.readline()

    assert client.post('/logout')[0] in [302, 303]

    # The stream ends within the check interval (and a few seconds of polling)
    start = time.time()
    while response.readline():
        assert time.time() - start < 8
    connection.close()
