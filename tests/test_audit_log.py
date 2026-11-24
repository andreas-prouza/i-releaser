"""Audit log of security events (docs/features/audit-log.md)"""
import json, os, sqlite3

import pytest

from web_server import Web_Server


@pytest.fixture(scope='module')
def server():
    s = Web_Server(settings="C_AUDIT_FILE = 'audit.jsonl'\n").start()
    yield s
    s.close()


def entries(server) -> list[dict]:
    with sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite')) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT * FROM audit_log ORDER BY id")]


def last(server, event: str) -> dict:
    return [e for e in entries(server) if e['event'] == event][-1]


def test_login_and_logout(server):

    client = server.client('runner')
    assert last(server, 'login')['user'] == 'runner'
    assert last(server, 'login')['client'] == '127.0.0.1'

    client.post('/logout')
    assert last(server, 'logout')['user'] == 'runner'

    server.client().login('nobody')
    failed = last(server, 'login_failed')
    assert failed['user'] == 'nobody' and failed['result'] == 'failed'


def test_token_events_without_the_token(server):

    client = server.client('intern')
    status, data = client.post_json('/api/generate_user_key')
    assert status == 200
    client.post('/api/drop_key')

    assert last(server, 'token_created')['user'] == 'intern'
    assert last(server, 'token_deleted')['user'] == 'intern'
    assert all(data['token'] not in json.dumps(e) for e in entries(server))


def test_permission_change_names_what_has_changed(server):

    boss = server.client('boss')
    _, state = boss.post_json('/api/add_permission', {'type': 'user', 'name': 'anna', 'general': ['read']})

    status, body = boss.post_json('/api/save_permissions', {'user_permissions': {'anna': {'roles': [], 'permissions': {'general': ['read', 'run'], 'workflows': {}}}}})
    assert status == 200, body

    change = last(server, 'permissions_changed')
    assert change['object'] == 'user anna'
    assert json.loads(change['details']) == {'added': ['general: run'], 'removed': []}


def test_setting_change(server):

    boss = server.client('boss')
    boss.post_json('/api/set_processing_mode/service')
    boss.post_json('/api/set_processing_mode/thread')

    change = last(server, 'setting_changed')
    assert change['object'] == 'C_PROCESSING_MODE'
    assert json.loads(change['details']) == {'old': 'service', 'new': 'thread'}


def test_file_for_a_siem(server):

    server.client('boss')

    with open(os.path.join(server.web_dir, 'audit.jsonl')) as f:
        lines = [json.loads(line) for line in f]

    assert lines[-1]['event'] == 'login' and lines[-1]['user'] == 'boss'


def test_audit_page_and_chain(server):

    boss = server.client('boss')
    boss.create_deployment('hidden_wf')

    status, _, page = boss.get('/settings/audit', headers={'Accept': 'text/html'})
    assert status == 200
    assert 'The audit log is complete' in page
    data = json.loads(page.split('id="audit-data">')[1].split('</script>')[0])
    assert {'login', 'deployment: create_workflow'} <= {row['event'] for row in data}

    assert server.client('runner').get('/settings/audit', headers={'Accept': 'text/html'})[0] == 403

    status, headers, csv = boss.get('/settings/audit.csv')
    assert status == 200 and csv.startswith('time (UTC),user,client,event')

    # A changed entry is detected
    with sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite')) as conn:
        conn.execute("UPDATE audit_log SET user = 'someone' WHERE id = (SELECT min(id) FROM audit_log)")

    _, _, page = boss.get('/settings/audit', headers={'Accept': 'text/html'})
    assert 'The audit log has been changed' in page


def test_two_factor_and_admin_events(server):

    from modules import totp

    runner = server.client('runner')
    _, setup = runner.post_json('/api/mfa/setup')
    _, enabled = runner.post_json('/api/mfa/enable', {'code': totp.get_code(setup['secret'], totp.get_step())})
    assert last(server, '2fa_enabled')['user'] == 'runner'

    runner.post_json('/api/mfa/recovery_codes')
    assert last(server, '2fa_recovery_codes')['user'] == 'runner'

    _, token = runner.post_json('/api/generate_user_key')

    boss = server.client('boss')
    assert boss.post('/api/revoke_token/runner')[0] == 200
    assert last(server, 'token_revoked')['object'] == 'runner'

    assert boss.post('/api/mfa/reset/runner')[0] == 200
    assert last(server, '2fa_reset')['object'] == 'runner'

    log = sorted(os.listdir(os.path.join(server.web_dir, 'log')))[0]
    boss.get(f"/log/{log}/10", headers={'Accept': 'text/html'})
    assert last(server, 'log_viewed')['object'] == log

    # No recovery code or secret is stored
    text = json.dumps(entries(server))
    assert setup['secret'] not in text and all(code not in text for code in enabled['recovery_codes'])


def test_blocked_and_unblocked_login():

    server = Web_Server(settings="C_LOGIN_CLIENT_MAX_FAILURES = 1\n").start()
    try:
        server.client().login('nobody')
        server.client().login('boss')
        assert last(server, 'login_blocked')['user'] == 'boss'
    finally:
        server.close()
