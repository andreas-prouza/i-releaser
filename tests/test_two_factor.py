"""Two-factor authentication with TOTP (docs/features/two-factor-authentication.md)"""
import base64, json, os, time

import pytest

from web_server import Web_Server

from modules import totp


#---------------------------------------------------------
# TOTP (RFC 6238)
#---------------------------------------------------------

# RFC 6238, appendix B: the secret of SHA1 and the 8 digit codes
RFC_SECRET = base64.b32encode(b'12345678901234567890').decode()
RFC_VECTORS = [(59, '94287082'), (1111111109, '07081804'), (1111111111, '14050471'), (1234567890, '89005924'), (2000000000, '69279037'), (20000000000, '65353130')]


@pytest.mark.parametrize('timestamp, code', RFC_VECTORS)
def test_rfc_6238_test_vectors(timestamp, code):
    assert totp.get_code(RFC_SECRET, totp.get_step(timestamp), digits=8) == code


def test_codes_of_the_previous_and_next_step_are_accepted():

    secret = totp.generate_secret()
    now = 1_700_000_000
    step = totp.get_step(now)

    for offset in [-1, 0, 1]:
        assert totp.verify(secret, totp.get_code(secret, step + offset), timestamp=now) == step + offset

    assert totp.verify(secret, totp.get_code(secret, step + 2), timestamp=now) is None
    assert totp.verify(secret, totp.get_code(secret, step - 2), timestamp=now) is None


def test_a_code_is_accepted_only_once():

    secret = totp.generate_secret()
    now = 1_700_000_000
    step = totp.get_step(now)
    code = totp.get_code(secret, step)

    assert totp.verify(secret, code, last_step=step, timestamp=now) is None
    assert totp.verify(secret, totp.get_code(secret, step + 1), last_step=step, timestamp=now) == step + 1


@pytest.mark.parametrize('code', [None, '', '12345', '1234567', 'abcdef', ' 12 345'])
def test_invalid_formats(code):
    assert totp.verify(totp.generate_secret(), code) is None


def test_secret_and_uri():

    secret = totp.generate_secret()

    assert len(base64.b32decode(secret + '=' * (-len(secret) % 8))) == 20
    assert totp.get_uri('anna', secret).startswith('otpauth://totp/i-Releaser%3Aanna?secret=' + secret)
    assert totp.get_qr_code(totp.get_uri('anna', secret)).startswith('data:image/svg+xml;base64,')


def test_template_of_the_settings_sets_no_policy():
    """docs/bugfixes/2fa-policy-set-by-update.md: setup3.13.sh copies the template into existing installations too"""

    from web_server import ROOT_DIR

    settings = {}
    with open(os.path.join(ROOT_DIR, 'etc', 'examples', 'settings.py'), encoding='utf-8') as f:
        exec(f.read(), settings)

    assert 'C_2FA_POLICY' not in settings


def test_recovery_codes():

    codes = totp.generate_recovery_codes()

    assert len(set(codes)) == 10
    assert totp.hash_recovery_code(codes[0].upper().replace('-', ' ')) == totp.hash_recovery_code(codes[0])



#---------------------------------------------------------
# In the web app
#---------------------------------------------------------

STUB = '''
class Connection:
    def close(self):
        pass

def connect(connection_string, **kwargs):
    import os
    with open(os.environ['ODBC_LOG'], 'a') as f:
        f.write(connection_string + "\\n")
    if connection_string.endswith('pwd=right'):
        return Connection()
    raise Exception('Connection refused')
'''


def start_server(tmp_path, settings: str='') -> Web_Server:

    (tmp_path / 'pyodbc.py').write_text(STUB)
    log = tmp_path / 'odbc.log'
    log.write_text('')

    s = Web_Server(settings=settings, env={'I_RELEASER_LOCAL_DEBUGGING': 'False', 'PYTHONPATH': str(tmp_path), 'ODBC_LOG': str(log)}).start()
    s.odbc_log = log
    return s


@pytest.fixture()
def server(tmp_path):
    s = start_server(tmp_path)
    yield s
    s.close()


def sign_ons(server) -> int:
    return len(server.odbc_log.read_text().splitlines())


def set_up(client) -> tuple[str, int, list[str]]:
    """Sets up the two-factor authentication of the logged-in client. Returns the secret, the step used and the recovery codes."""

    status, setup = client.post_json('/api/mfa/setup')
    assert status == 200, setup
    assert setup['qr_code'].startswith('data:image/svg+xml;base64,')

    step = totp.get_step()
    status, enabled = client.post_json('/api/mfa/enable', {'code': totp.get_code(setup['secret'], step)})
    assert status == 200, enabled

    return setup['secret'], step, enabled['recovery_codes']


def session_file(server, client) -> str:
    return os.path.join(server.web_dir, 'sessions', f"{client.session_id}.json")


def test_login_needs_the_code_after_the_setup(server):

    admin = server.client()
    assert admin.login('boss', 'right') == 200
    secret, step, _ = set_up(admin)

    without_code = server.client()
    without_code.login('boss', 'right')
    assert without_code.get('/workflows')[0] == 401

    with_code = server.client()
    # The code of the setup can't be used again: the one of the next step
    assert with_code.login('boss', 'right', totp.get_code(secret, step + 1)) == 200
    assert with_code.get('/workflows')[0] == 200

    again = server.client()
    again.login('boss', 'right', totp.get_code(secret, step + 1))
    assert again.get('/workflows')[0] == 401


def test_wrong_code_does_not_reach_the_ibm_i(server):

    admin = server.client()
    admin.login('boss', 'right')
    set_up(admin)
    before = sign_ons(server)

    for code in ['000000', 'aaaa-bbbb-cc']:
        server.client().login('boss', 'right', code)

    assert sign_ons(server) == before


def test_recovery_code_logs_in_once_and_isnt_lost_by_a_wrong_password(server):

    admin = server.client()
    admin.login('boss', 'right')
    _, _, codes = set_up(admin)

    # A wrong password doesn't use up the recovery code
    server.client().login('boss', 'wrong', codes[0])

    first = server.client()
    assert first.login('boss', 'right', codes[0]) == 200
    assert first.get('/workflows')[0] == 200

    second = server.client()
    second.login('boss', 'right', codes[0])
    assert second.get('/workflows')[0] == 401


def test_too_many_wrong_codes_block_the_codes(tmp_path):

    server = start_server(tmp_path, settings="C_2FA_MAX_FAILURES = 2\n")
    try:
        admin = server.client()
        admin.login('boss', 'right')
        _, _, codes = set_up(admin)

        for _ in range(2):
            server.client().login('boss', 'right', '000000')

        # Even a valid code isn't accepted now
        client = server.client()
        client.login('boss', 'right', codes[0])
        assert client.get('/workflows')[0] == 401
    finally:
        server.close()


def test_required_policy_allows_only_the_setup(tmp_path):

    server = start_server(tmp_path, settings="C_2FA_POLICY = 'required'\n")
    try:
        client = server.client()
        assert client.login('runner', 'right') == 200

        status, headers, _ = client.get('/workflows', headers={'Accept': 'text/html'})
        assert status == 303 and headers['location'] == '/user#two-factor'
        assert client.get('/api/get_workflows')[0] == 403

        _, _, page = client.get('/user', headers={'Accept': 'text/html'})
        assert 'data-action="mfa-setup"' in page
        assert 'data-action="mfa-disable"' not in page

        set_up(client)
        assert client.get('/api/get_workflows')[0] == 200

        # Required: can't be turned off
        assert client.post_json('/api/mfa/disable', {'code': '000000'})[0] == 409
    finally:
        server.close()


@pytest.mark.parametrize('policy', ['off', 'optional'])
def test_loosened_policy_ends_the_setup_requirement_of_a_session(tmp_path, policy):
    """docs/bugfixes/2fa-setup-flag-outlives-policy.md: the session of the login doesn't stay on the setup page"""

    server = start_server(tmp_path, settings="C_2FA_POLICY = 'required'\n")
    try:
        client = server.client()
        client.login('runner', 'right')
        assert client.get('/api/get_workflows')[0] == 403

        server.stop()
        with open(server.path('etc', 'settings.py'), 'w') as f:
            f.write(f"C_2FA_POLICY = '{policy}'\n")
        server.start()

        # The same session, without a new login
        assert client.get('/api/get_workflows')[0] == 200
        status, _, page = client.get('/user', headers={'Accept': 'text/html'})
        assert status == 200 and 'Two-factor authentication is required for you' not in page

        # The flag is gone from the session, not only ignored
        with open(session_file(server, client)) as f:
            assert 'mfa_setup_required' not in json.load(f)['session-data']
    finally:
        server.close()


def test_admins_policy(tmp_path):

    server = start_server(tmp_path, settings="C_2FA_POLICY = 'admins'\n")
    try:
        runner = server.client()
        runner.login('runner', 'right')
        assert runner.get('/api/get_workflows')[0] == 200

        boss = server.client()
        boss.login('boss', 'right')
        assert boss.get('/api/get_workflows')[0] == 403
    finally:
        server.close()


def test_step_up_for_a_new_token(server):

    client = server.client()
    client.login('runner', 'right')
    secret, step, codes = set_up(client)

    # Right after the setup: the code is recent
    assert client.post_json('/api/generate_user_key')[0] == 200

    # Some time later
    path = session_file(server, client)
    with open(path) as f:
        data = json.load(f)
    data['session-data']['mfa_at'] = time.time() - 3600
    with open(path, 'w') as f:
        json.dump(data, f)

    status, body = client.post_json('/api/generate_user_key')
    assert status == 403 and body['step_up'] is True

    assert client.post_json('/api/mfa/verify', {'code': '000000'})[0] == 422
    assert client.post_json('/api/mfa/verify', {'code': codes[0]})[0] == 200
    assert client.post_json('/api/generate_user_key')[0] == 200


def test_step_up_for_a_setting_of_the_web_app(server):
    """docs/features/settings-in-web-app.md: a change and a reset need a recent code"""

    admin = server.client()
    admin.login('boss', 'right')
    secret, step, codes = set_up(admin)

    path = session_file(server, admin)
    with open(path) as f:
        data = json.load(f)
    data['session-data']['mfa_at'] = time.time() - 3600
    with open(path, 'w') as f:
        json.dump(data, f)

    status, body = admin.post_json('/api/settings/C_RETENTION_DAYS', {'value': 30})
    assert status == 403 and body['step_up'] is True
    status, body = admin.request('DELETE', '/api/settings/C_RETENTION_DAYS')[:2]
    assert status == 403

    assert admin.post_json('/api/mfa/verify', {'code': codes[0]})[0] == 200
    assert admin.post_json('/api/settings/C_RETENTION_DAYS', {'value': 30})[0] == 200
    assert admin.request('DELETE', '/api/settings/C_RETENTION_DAYS')[0] == 200



def test_token_requests_can_not_manage_the_account(server):

    client = server.client()
    client.login('runner', 'right')
    status, data = client.post_json('/api/generate_user_key')
    assert status == 200

    api = server.client()
    api.headers['Authorization'] = f"Bearer {data['token']}"

    assert api.post('/api/generate_user_key')[0] == 403
    assert api.post('/api/drop_key')[0] == 403
    assert api.post('/api/mfa/setup')[0] == 403


def test_turn_off_with_a_code(server):

    client = server.client()
    client.login('runner', 'right')
    _, _, codes = set_up(client)

    assert client.post_json('/api/mfa/disable', {'code': '000000'})[0] == 422
    assert client.post_json('/api/mfa/disable', {'code': codes[0]})[0] == 200

    other = server.client()
    assert other.login('runner', 'right') == 200
    assert other.get('/api/get_workflows')[0] == 200


def test_admin_resets_the_two_factor_authentication(server):

    runner = server.client()
    runner.login('runner', 'right')
    set_up(runner)

    admin = server.client()
    admin.login('boss', 'right')

    _, _, page = admin.get('/settings/security', headers={'Accept': 'text/html'})
    assert 'data-action="reset-mfa" data-user="runner"' in page

    assert runner.post('/api/mfa/reset/runner')[0] == 403
    assert admin.post('/api/mfa/reset/runner')[0] == 200
    assert admin.post('/api/mfa/reset/runner')[0] == 404

    client = server.client()
    assert client.login('runner', 'right') == 200
    assert client.get('/api/get_workflows')[0] == 200


def test_credentials_only_on_the_login_page(server):
    """docs/bugfixes/minor-web-defects-2026-11.md, item 1"""

    client = server.client()
    status, _, _ = client.request('POST', '/workflows', form={'user': 'boss', 'password': 'right'}, headers={'Accept': 'text/html'})

    assert sign_ons(server) == 0
    assert client.get('/api/get_workflows')[0] == 401


def test_login_form_of_another_site_is_refused(server):

    client = server.client()
    client.origin = 'https://evil.example'

    status, _, _ = client.request('POST', '/login', form={'user': 'boss', 'password': 'right'})

    assert status == 403
    assert sign_ons(server) == 0
