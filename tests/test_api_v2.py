"""Web API v2 (docs/features/api-v2.md)"""
import json, os, sqlite3

import pytest

from web_server import WORKFLOWS, Web_Server
from test_four_eyes_check import EYES_WF, TEAM


@pytest.fixture(scope='module')
def server():
    s = Web_Server(workflows={**WORKFLOWS, 'eyes_wf': EYES_WF}, users=TEAM).start()
    yield s
    s.close()


def call(client, method: str, path: str, body=None) -> tuple[int, dict|None, dict]:
    status, headers, text = client.request(method, path, body=body)
    return status, (json.loads(text) if text else None), headers


def create(client, workflow: str='seq_wf', **values) -> dict:
    status, data, _ = call(client, 'POST', '/api/v2/deployments', {'workflow': workflow, **values})
    assert status == 201, data
    return data


def stage_id(deployment: dict, name: str) -> int:
    general = deployment['general']
    return {s['name']: s['id'] for s in general['open_stages'] + general['processed_stages']}[name]


def get(client, deployment_id: int) -> dict:
    status, data, _ = call(client, 'GET', f"/api/v2/deployments/{deployment_id}")
    assert status == 200, data
    return data


def db(server):
    conn = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'))
    conn.row_factory = sqlite3.Row
    return conn


def assert_error(status: int, data: dict, expected: int, text: str='') -> None:
    assert status == expected, data
    assert data['status'] == 'error' and text in data['message'], data



#---------------------------------------------------------
# Deployments
#---------------------------------------------------------

def test_create_and_get(server):

    boss = server.client('boss')
    created = create(boss, custom_data={'ticket': 'ABC-1'}, compiles=[{'source': 'a.rpgle'}])

    assert created['general']['project'] == 'seq' and created['general']['status'] == 'ready'
    assert created['custom_data'] == {'ticket': 'ABC-1'}

    data = get(boss, created['general']['id'])
    assert data['general']['id'] == created['general']['id']

    with db(server) as conn:
        assert conn.execute("SELECT action FROM processing_users WHERE meta_file_id = ?", (created['general']['id'],)).fetchone()['action'] == 'create_workflow'


def test_list_with_pages(server):

    boss = server.client('boss')
    ids = [create(boss, 'hidden_wf')['general']['id'] for _ in range(3)]

    status, first, _ = call(boss, 'GET', '/api/v2/deployments?project=hidden&limit=2')
    assert status == 200
    assert [d['id'] for d in first['items']] == ids[::-1][:2]
    assert first['next_cursor']
    assert set(first['items'][0]) == {'id', 'project', 'version', 'workflow', 'status', 'commit', 'create_time', 'update_time'}

    status, second, _ = call(boss, 'GET', f"/api/v2/deployments?project=hidden&limit=2&cursor={first['next_cursor']}")
    assert status == 200
    assert ids[0] in [d['id'] for d in second['items']]
    assert not set(d['id'] for d in second['items']) & set(d['id'] for d in first['items'])

    status, ready, _ = call(boss, 'GET', '/api/v2/deployments?project=hidden&status=canceled')
    assert ready['items'] == [] and ready['next_cursor'] is None

    for query, text in [('limit=0', "'limit'"), ('limit=501', "'limit'"), ('cursor=%21%21', 'Invalid cursor'), ('status=lost', "Status 'lost'")]:
        assert_error(*call(boss, 'GET', f"/api/v2/deployments?{query}")[:2], 422, text)


def test_list_only_readable_workflows(server):

    boss = server.client('boss')
    hidden = create(boss, 'hidden_wf')['general']['id']

    _, data, _ = call(server.client('stranger'), 'GET', '/api/v2/deployments?limit=500')
    assert hidden not in [d['id'] for d in data['items']]
    assert {d['workflow'] for d in data['items']} <= {'seq_wf'}


def test_unknown_field_is_refused(server):

    status, data, _ = call(server.client('boss'), 'POST', '/api/v2/deployments', {'workflow': 'seq_wf', 'custm_data': {}})
    assert_error(status, data, 422, 'custm_data')


def test_permissions(server):

    boss = server.client('boss')
    deployment = create(boss)
    path = f"/api/v2/deployments/{deployment['general']['id']}"

    intern = server.client('intern')
    assert_error(*call(intern, 'POST', f"{path}/cancel")[:2], 403)
    assert_error(*call(intern, 'POST', f"{path}/stages/{stage_id(deployment, 'START')}/runs", {})[:2], 403)
    assert_error(*call(server.client('stranger'), 'POST', '/api/v2/deployments', {'workflow': 'seq_wf'})[:2], 403)
    assert_error(*call(server.client('stranger'), 'GET', f"/api/v2/deployments/{create(boss, 'hidden_wf')['general']['id']}")[:2], 403)

    # Without login
    status, data, _ = call(server.client(), 'GET', '/api/v2/deployments')
    assert status == 401


def test_not_found(server):

    boss = server.client('boss')
    deployment = create(boss)
    path = f"/api/v2/deployments/{deployment['general']['id']}"

    assert_error(*call(boss, 'GET', '/api/v2/deployments/999999')[:2], 404, 'Deployment 999999 not found')
    assert_error(*call(boss, 'POST', f"{path}/stages/999999/runs", {})[:2], 404, 'Stage 999999')
    assert_error(*call(boss, 'GET', f"{path}/steps/999999/log")[:2], 404, 'Step 999999')
    assert_error(*call(boss, 'DELETE', '/api/v2/jobs/999999')[:2], 404)
    assert_error(*call(boss, 'GET', '/api/v2/nothing')[:2], 404)
    assert_error(*call(boss, 'GET', '/api/v2/jobs/1')[:2], 405)



#---------------------------------------------------------
# Stages and steps
#---------------------------------------------------------

def test_run_a_stage_and_read_its_log(server):

    boss = server.client('boss')
    # Deployments of par_wf don't wait for each other
    deployment = create(boss, 'par_wf')
    deployment_id = deployment['general']['id']

    # Not ready yet
    assert_error(*call(boss, 'POST', f"/api/v2/deployments/{deployment_id}/stages/{stage_id(deployment, 'A')}/runs", {})[:2], 409)
    assert_error(*call(boss, 'POST', f"/api/v2/deployments/{deployment_id}/stages/{stage_id(deployment, 'START')}/runs", {'mode': 'some'})[:2], 422)

    status, data, _ = call(boss, 'POST', f"/api/v2/deployments/{deployment_id}/stages/{stage_id(deployment, 'START')}/runs", {'mode': 'all'})
    assert status == 202 and data['mode'] == 'thread', data
    boss.wait_for_stage(deployment_id, 'START')

    start = next(s for s in get(boss, deployment_id)['general']['processed_stages'] if s['name'] == 'START')
    step = start['actions'][0]
    status, log, _ = call(boss, 'GET', f"/api/v2/deployments/{deployment_id}/steps/{step['id']}/log")
    assert status == 200 and 'quick' in log['items'][-1]['stdout']

    status, history, _ = call(boss, 'GET', f"/api/v2/deployments/{deployment_id}/history")
    assert 'run_stage' in [entry['action'] for entry in history['items']]

    status, jobs, _ = call(boss, 'GET', f"/api/v2/deployments/{deployment_id}/jobs")
    assert status == 200 and jobs == {'items': [], 'next_cursor': None}

    # Back to ready
    status, data, _ = call(boss, 'POST', f"/api/v2/deployments/{deployment_id}/stages/{start['id']}/reset", {'kind': 'last-finished'})
    assert status == 200 and data == {'id': start['id'], 'name': 'START', 'status': 'ready'}
    assert_error(*call(boss, 'POST', f"/api/v2/deployments/{deployment_id}/stages/{start['id']}/reset", {'kind': 'hanging'})[:2], 409)


def test_check_error_of_a_step(server):

    boss = server.client('boss')
    deployment = create(boss)
    deployment_id = deployment['general']['id']
    step = next(s for s in deployment['general']['open_stages'] if s['name'] == 'PROD')['actions'][0]

    status, data, _ = call(boss, 'PATCH', f"/api/v2/deployments/{deployment_id}/steps/{step['id']}", {'check_error': False})
    assert status == 200 and data == {'id': step['id'], 'check_error': False}

    with db(server) as conn:
        assert conn.execute("SELECT check_error FROM actions WHERE id = ?", (step['id'],)).fetchone()[0] == 0

    assert_error(*call(boss, 'PATCH', f"/api/v2/deployments/{deployment_id}/steps/{step['id']}", {'check_error': 'no'})[:2], 422)



#---------------------------------------------------------
# Changes
#---------------------------------------------------------

def test_custom_data(server):

    boss = server.client('boss')
    deployment_id = create(boss, custom_data={'ticket': 'A', 'other': 1})['general']['id']

    status, data, _ = call(boss, 'PATCH', f"/api/v2/deployments/{deployment_id}/custom-data", {'fields': {'$.ticket': 'B'}})
    assert status == 200 and data == {'changed': ['$.ticket'], 'custom_data': {'ticket': 'B', 'other': 1}}

    assert_error(*call(boss, 'PATCH', f"/api/v2/deployments/{deployment_id}/custom-data", {'fields': {'$.other': 2}})[:2], 422, 'not editable')
    assert_error(*call(boss, 'PATCH', f"/api/v2/deployments/{deployment_id}/custom-data", {'fields': {}})[:2], 422)


def test_objects(server):

    boss = server.client('boss')
    deployment_id = create(boss)['general']['id']

    assert_error(*call(boss, 'PATCH', f"/api/v2/deployments/{deployment_id}/objects", {'objects': [], 'ready': True})[:2], 422)
    assert_error(*call(boss, 'PATCH', f"/api/v2/deployments/{deployment_id}/objects",
                       {'objects': [{'lib': 'L', 'name': 'N', 'type': 'pgm'}], 'ready': True})[:2], 404, '1 objects not found')


def test_cancel(server):

    boss = server.client('boss')
    deployment_id = create(boss)['general']['id']

    status, data, _ = call(boss, 'POST', f"/api/v2/deployments/{deployment_id}/cancel")
    assert status == 200 and data['general']['status'] == 'canceled'

    assert_error(*call(boss, 'POST', f"/api/v2/deployments/{deployment_id}/cancel")[:2], 409)



#---------------------------------------------------------
# v1 and v2
#---------------------------------------------------------

def test_v1_and_v2_give_the_same_result(server):

    boss = server.client('boss')
    v1 = boss.create_deployment('seq_wf', {'ticket': 'X'})
    v2 = create(boss, custom_data={'ticket': 'X'})['general']['id']

    assert boss.post_json(f"/api/cancel_deployment/{v1}")[0] == 200
    assert call(boss, 'POST', f"/api/v2/deployments/{v2}/cancel")[0] == 200

    with db(server) as conn:
        rows = {row['id']: dict(row) for row in conn.execute("SELECT id, status, custom_data FROM meta_files WHERE id IN (?, ?)", (v1, v2))}
        history = [[row['action'] for row in conn.execute("SELECT action FROM processing_users WHERE meta_file_id = ? ORDER BY id", (d,))] for d in (v1, v2)]

    assert rows[v1]['status'] == rows[v2]['status'] == 'canceled'
    assert rows[v1]['custom_data'] == rows[v2]['custom_data']
    assert history[0] == history[1] == ['create_workflow', 'cancel_workflow']

    v1_page = boss.get_deployment(v1)
    assert set(v1_page) == set(get(boss, v2))


def test_v1_is_deprecated(server):

    boss = server.client('boss')

    _, headers, _ = boss.get('/api/get_workflows')
    assert headers.get('deprecation') == 'true'

    _, headers, _ = boss.get('/api/v2/workflows')
    assert 'deprecation' not in headers


def test_openapi_has_only_v2(server):

    status, _, text = server.client('boss').get('/openapi.json')
    assert status == 200
    spec = json.loads(text)

    assert spec['paths'] and all(path.startswith('/api/v2/') for path in spec['paths'])
    assert spec['components']['securitySchemes']['HTTPBearer'] == {'type': 'http', 'scheme': 'bearer', 'description': "API token of the page 'My account'"}
    assert 'Deployment_Create' in spec['components']['schemas']


def test_with_a_token(server):

    boss = server.client('boss')
    status, data = boss.post_json('/api/generate_user_key')
    assert status == 200

    status, _, text = server.client().request('GET', '/api/v2/workflows', headers={'Authorization': f"Bearer {data['token']}"})
    assert status == 200 and 'seq_wf' in text



#---------------------------------------------------------
# Tokens (docs/features/api-v2.md#tokens)
#---------------------------------------------------------

def bearer(server, token: str):
    client = server.client()
    client.headers['Authorization'] = f"Bearer {token}"
    return client


def test_tokens_with_name_scope_and_expiry(server):

    from datetime import datetime, timedelta, timezone

    boss = server.client('boss')
    status, created, _ = call(boss, 'POST', '/api/v2/tokens', {'name': 'CI read', 'scope': 'read', 'expires_in_days': 30})
    assert status == 201, created
    token = created['token']
    assert token.startswith('irt_') and created['name'] == 'CI read' and created['scope'] == 'read'
    assert created['expires_at'][:10] == (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()

    status, listed, _ = call(boss, 'GET', '/api/v2/tokens')
    mine = [t for t in listed['items'] if t['id'] == created['id']][0]
    # Never the token or its hash again
    assert 'token' not in mine and 'key_hash' not in mine and mine['masked'].endswith(token[-6:])

    assert_error(*call(boss, 'POST', '/api/v2/tokens', {'name': 'CI read'})[:2], 409, 'already')

    # Scope read: only GET, also of v1
    reader = bearer(server, token)
    assert call(reader, 'GET', '/api/v2/deployments')[0] == 200
    assert_error(*call(reader, 'POST', '/api/v2/deployments', {'workflow': 'seq_wf'})[:2], 403, "scope 'read'")
    assert_error(*call(reader, 'POST', '/api/start_workflow/seq_wf', {})[:2], 403, "scope 'read'")

    # The reads of v1 with POST, as the OBI extension sends them
    deployment_id = create(boss)['general']['id']
    status, data, _ = call(reader, 'POST', f"/api/get_meta_file_json/{deployment_id}")
    assert status == 200 and data['general']['id'] == deployment_id
    status, data, _ = call(reader, 'POST', '/api/list_deployments/seq')
    assert status == 200 and deployment_id in [d['meta_file_id'] for d in data]
    # Not the actions of a deployment
    assert_error(*call(reader, 'POST', f"/api/cancel_deployment/{deployment_id}")[:2], 403, "scope 'read'")
    assert_error(*call(reader, 'POST', f"/api/get_meta_file_json/{deployment_id}/../../cancel_deployment/{deployment_id}")[:2], 403)

    # A token can't create or delete tokens
    assert_error(*call(reader, 'GET', '/api/v2/tokens')[:2], 403, 'not with an API token')
    assert_error(*call(reader, 'DELETE', f"/api/v2/tokens/{created['id']}")[:2], 403, "scope 'read'")

    status, _, _ = call(boss, 'DELETE', f"/api/v2/tokens/{created['id']}")
    assert status == 204
    assert call(reader, 'GET', '/api/v2/deployments')[0] == 401


@pytest.mark.parametrize('body, text', [
    ({'name': ''}, 'needs a name'),
    ({'name': 'a\tb'}, 'control characters'),
    ({'name': 'x' * 65}, 'name'),
    ({'name': 'x', 'scope': 'admin'}, 'scope'),
    ({'name': 'x', 'expires_in_days': 0}, '1 to 365'),
    ({'name': 'x', 'expires_in_days': 366}, '1 to 365'),
    ({'name': 'x', 'expire_days': 3}, 'expire_days'),
])
def test_invalid_token(server, body, text):
    assert_error(*call(server.client('boss'), 'POST', '/api/v2/tokens', body)[:2], 422, text)


def test_admin_revokes_the_token_of_another_user(server):

    runner = server.client('runner')
    status, created, _ = call(runner, 'POST', '/api/v2/tokens', {'name': 'Pipeline'})
    assert status == 201

    # Another user doesn't see that it exists
    assert_error(*call(server.client('intern'), 'DELETE', f"/api/v2/tokens/{created['id']}")[:2], 404)

    _, _, page = server.client('boss').get('/settings', headers={'Accept': 'text/html'})
    assert f'data-token-id="{created["id"]}"' in page and 'Pipeline' in page

    assert call(server.client('boss'), 'DELETE', f"/api/v2/tokens/{created['id']}")[0] == 204
    assert call(bearer(server, created['token']), 'GET', '/api/v2/workflows')[0] == 401

    with db(server) as conn:
        assert conn.execute("SELECT count(*) FROM audit_log WHERE event = 'token_revoked' AND object = 'runner'").fetchone()[0] >= 1


def test_tokens_of_keys_json_are_taken_over_at_the_start():

    import hashlib

    token = 'irt_' + 'k' * 43
    s = Web_Server()
    try:
        with open(os.path.join(s.web_dir, 'etc', 'keys.json'), 'w') as f:
            json.dump({'boss': {'key': hashlib.sha256(token.encode()).hexdigest(), 'orig_key_masked': '****kkkkkk',
                                'date': '2026-01-01 10:00:00.123456', 'expires': '2099-01-01T10:00:00', 'last_used': '2026-02-01 10:00:00'}}, f)
        s.start()

        assert not os.path.exists(os.path.join(s.web_dir, 'etc', 'keys.json'))
        assert os.path.exists(os.path.join(s.web_dir, 'etc', 'keys.json.migrated'))

        with db(s) as conn:
            row = dict(conn.execute("SELECT * FROM api_tokens WHERE user = 'boss'").fetchone())
        assert row['name'] == 'API token' and row['scope'] == 'write' and row['expires_at'].startswith('2099-01-01')

        assert call(bearer(s, token), 'GET', '/api/v2/workflows')[0] == 200
    finally:
        s.close()



#---------------------------------------------------------
# Each endpoint of a deployment: not found, permission missing
#---------------------------------------------------------

ENDPOINTS = [
    ('GET', '/api/v2/deployments/{id}', None),
    ('POST', '/api/v2/deployments/{id}/cancel', None),
    ('POST', '/api/v2/deployments/{id}/reset', None),
    ('PATCH', '/api/v2/deployments/{id}/custom-data', {'fields': {'$.ticket': 'X'}}),
    ('PATCH', '/api/v2/deployments/{id}/objects', {'objects': [{'lib': 'L', 'name': 'N', 'type': 'T'}], 'ready': True}),
    ('GET', '/api/v2/deployments/{id}/history', None),
    ('GET', '/api/v2/deployments/{id}/jobs', None),
    ('POST', '/api/v2/deployments/{id}/stages/{stage}/runs', {}),
    ('POST', '/api/v2/deployments/{id}/stages/{stage}/reset', {'kind': 'hanging'}),
    ('POST', '/api/v2/deployments/{id}/stages/{stage}/approvals', None),
    ('PATCH', '/api/v2/deployments/{id}/steps/{step}', {'check_error': False}),
    ('GET', '/api/v2/deployments/{id}/steps/{step}/log', None),
]


@pytest.mark.parametrize('method, path, body', ENDPOINTS)
def test_every_endpoint_answers_not_found(server, method, path, body):
    assert_error(*call(server.client('boss'), method, path.format(id=999999, stage=1, step=1), body)[:2], 404)


@pytest.fixture(scope='module')
def hidden(server) -> dict:
    """A deployment which the user stranger may not read"""
    deployment = create(server.client('boss'), 'hidden_wf')
    start = deployment['general']['open_stages'][0]
    return {'id': deployment['general']['id'], 'stage': start['id'], 'step': start['actions'][0]['id']}


@pytest.mark.parametrize('method, path, body', ENDPOINTS)
def test_every_endpoint_checks_the_permission(server, hidden, method, path, body):
    assert_error(*call(server.client('stranger'), method, path.format(**hidden), body)[:2], 403)



def test_projects(server):

    boss = server.client('boss')
    create(boss)

    status, data, _ = call(boss, 'GET', '/api/v2/projects')
    seq = [p for p in data['items'] if p['name'] == 'seq'][0]
    assert status == 200 and sum(seq['deployments'].values()) >= 1

    # Only projects of readable workflows
    _, data, _ = call(server.client('stranger'), 'GET', '/api/v2/projects')
    assert [p['name'] for p in data['items']] == ['seq']


def test_reset_a_deployment(server):

    boss = server.client('boss')
    deployment_id = create(boss)['general']['id']

    status, data, _ = call(boss, 'POST', f"/api/v2/deployments/{deployment_id}/reset")
    assert status == 200 and data['general']['status'] == 'ready'

    call(boss, 'POST', f"/api/v2/deployments/{deployment_id}/cancel")
    assert_error(*call(boss, 'POST', f"/api/v2/deployments/{deployment_id}/reset")[:2], 409, 'canceled')


def test_custom_data_needs_its_permission(server):

    deployment_id = create(server.client('boss'))['general']['id']
    assert_error(*call(server.client('intern'), 'PATCH', f"/api/v2/deployments/{deployment_id}/custom-data", {'fields': {'$.ticket': 'B'}})[:2], 403)


def test_approve_a_stage(server):

    creator = server.client('creator')
    deployment = create(creator, 'eyes_wf')
    deployment_id = deployment['general']['id']
    creator.run_stage(deployment_id, 'START')
    creator.wait_for_stage(deployment_id, 'START')
    prod = creator.get_stages(deployment_id)['PROD']['id']

    assert_error(*call(creator, 'POST', f"/api/v2/deployments/{deployment_id}/stages/{prod}/runs", {})[:2], 409, 'approval')
    # The creator doesn't approve
    assert call(creator, 'POST', f"/api/v2/deployments/{deployment_id}/stages/{prod}/approvals")[0] in (403, 409)

    status, data, _ = call(server.client('checker'), 'POST', f"/api/v2/deployments/{deployment_id}/stages/{prod}/approvals")
    assert status == 201 and data['approved_by'] == 'checker'
    assert_error(*call(server.client('checker2'), 'POST', f"/api/v2/deployments/{deployment_id}/stages/{prod}/approvals")[:2], 409, 'approved already')

    assert call(creator, 'POST', f"/api/v2/deployments/{deployment_id}/stages/{prod}/runs", {})[0] == 202


def test_job_which_has_started_isnt_canceled(server):

    deployment = create(server.client('boss'), 'hidden_wf')
    with db(server) as conn:
        job = conn.execute("INSERT INTO processing_jobs (meta_file_id, stage_id, user, status, create_time) VALUES (?, ?, 'boss', 'running', '2026-11-24T10:00:00')",
                           (deployment['general']['id'], deployment['general']['open_stages'][0]['id'])).lastrowid

    assert_error(*call(server.client('boss'), 'DELETE', f"/api/v2/jobs/{job}")[:2], 409, 'not in the queue')
    assert_error(*call(server.client('stranger'), 'DELETE', f"/api/v2/jobs/{job}")[:2], 403)


def test_read_token_gets_403_for_every_change(server, hidden):

    status, created, _ = call(server.client('boss'), 'POST', '/api/v2/tokens', {'name': 'Every change', 'scope': 'read'})
    assert status == 201
    reader = bearer(server, created['token'])

    changes = [(m, p.format(**hidden), b) for m, p, b in ENDPOINTS if m != 'GET']
    changes += [('POST', '/api/v2/deployments', {'workflow': 'seq_wf'}), ('DELETE', '/api/v2/jobs/1', None),
                ('POST', '/api/v2/tokens', {'name': 'x'}), ('DELETE', f"/api/v2/tokens/{created['id']}", None)]

    for method, path, body in changes:
        assert_error(*call(reader, method, path, body)[:2], 403, "scope 'read'")

    # Nothing has changed
    assert get(server.client('boss'), hidden['id'])['general']['status'] == 'ready'
