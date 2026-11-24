"""The login with the password check: pyodbc is replaced by a stub which records the connection strings"""
import os, threading, time

import pytest

from web_server import Web_Server, wait_until


STUB = '''
class Connection:
    def close(self):
        pass

def connect(connection_string, **kwargs):
    import os, time
    with open(os.environ['ODBC_LOG'], 'a') as f:
        f.write(connection_string + "\\n")
    if connection_string.endswith('pwd=slow'):
        # The IBM i doesn't answer: the driver ends the sign-on after the login timeout (SQLSTATE HYT00, like pyodbc)
        time.sleep(kwargs.get('timeout') or 10)
        raise Exception('HYT00', 'Login timeout expired')
    if connection_string.endswith('pwd=right'):
        return Connection()
    raise Exception('Connection refused for: ' + connection_string)
'''


@pytest.fixture()
def server(tmp_path):

    (tmp_path / 'pyodbc.py').write_text(STUB)
    log = tmp_path / 'odbc.log'
    log.write_text('')

    s = Web_Server(settings="C_LOGIN_MAX_FAILURES = 3\nC_LOGIN_BLOCK_MINUTES = 1\n",
                   env={'I_RELEASER_LOCAL_DEBUGGING': 'False', 'PYTHONPATH': str(tmp_path), 'ODBC_LOG': str(log)}).start()
    s.odbc_log = log
    yield s
    s.close()



def get_connections(server) -> list[str]:
    return server.odbc_log.read_text().splitlines() if server.odbc_log.exists() else []



def is_signing_on(server) -> bool:
    """The driver has got the sign-on which hangs (it writes it before it waits)"""
    return any(connection.endswith('pwd=slow') for connection in get_connections(server))



def test_correct_password(server):

    client = server.client()
    client.login('boss', 'right')

    assert client.get('/settings')[0] == 200
    assert len(get_connections(server)) == 1



def test_password_can_not_add_keywords(server):

    client = server.client()
    client.login('boss', 'x;SYSTEM=other;UID=a;PWD=b')

    connections = get_connections(server)

    assert len(connections) == 1
    assert connections[0].endswith('uid=boss;pwd={x;SYSTEM=other;UID=a;PWD=b}')
    assert client.get('/settings')[0] == 401



def test_password_with_braces_is_quoted(server):

    server.client().login('boss', 'a}b')

    assert get_connections(server)[0].endswith('pwd={a}}b}')



@pytest.mark.parametrize('user', ['a;b', 'toolongusername', 'bo ss', '1boss', 'unknown'])
def test_invalid_users_are_not_tried(server, user):

    server.client().login(user, 'right')

    assert get_connections(server) == []



def test_control_characters_in_the_password_are_rejected(server):

    server.client().login('boss', 'ab\x01c')

    assert get_connections(server) == []



def test_failed_logins_are_blocked_without_connecting(server):

    for _ in range(3):
        server.client().login('boss', 'wrong')

    assert len(get_connections(server)) == 3

    client = server.client()
    _, _, text = client.request('POST', '/login', form={'user': 'boss', 'password': 'right'}, headers={'Accept': 'text/html'})

    # The same text as for a wrong password: it doesn't tell that the user exists
    assert 'Login failed. Check your user' in text
    assert len(get_connections(server)) == 3
    assert client.get('/settings')[0] == 401



def test_error_does_not_tell_what_was_wrong(server):

    _, _, wrong_password = server.client().request('POST', '/login', form={'user': 'boss', 'password': 'wrong'}, headers={'Accept': 'text/html'})
    _, _, unknown_user = server.client().request('POST', '/login', form={'user': 'unknown', 'password': 'wrong'}, headers={'Accept': 'text/html'})

    message = 'Login failed. Check your user'

    assert message in wrong_password
    assert message in unknown_user
    assert 'Connection refused' not in wrong_password



#---------------------------------------------------------
# login-can-disable-ibm-i-profiles (review 2026-11-23)
#---------------------------------------------------------

@pytest.fixture()
def strict_server(tmp_path):
    """The defaults: 2 failed sign-ons of a user block it; the client block ends after a short time"""

    (tmp_path / 'pyodbc.py').write_text(STUB)
    log = tmp_path / 'odbc.log'
    log.write_text('')

    s = Web_Server(settings="C_LOGIN_BLOCK_MINUTES = 0.02\nC_LOGIN_TIMEOUT_SECONDS = 1\nC_LOGIN_MAX_PARALLEL = 1\n",
                   env={'I_RELEASER_LOCAL_DEBUGGING': 'False', 'PYTHONPATH': str(tmp_path), 'ODBC_LOG': str(log)}).start()
    s.odbc_log = log
    yield s
    s.close()



def test_blocked_user_stays_blocked_after_the_block_time(strict_server):

    for _ in range(2):
        strict_server.client().login('runner', 'wrong')

    # A time has to pass: longer than C_LOGIN_BLOCK_MINUTES, the block of a client would have ended
    time.sleep(1.5)

    client = strict_server.client()
    client.login('runner', 'right')

    # A third sign-on would disable the profile with QMAXSIGN = 3
    assert len(get_connections(strict_server)) == 2
    assert client.get('/workflows')[0] == 401



def test_successful_login_clears_the_failures(strict_server):

    strict_server.client().login('runner', 'wrong')
    strict_server.client().login('runner', 'right')
    strict_server.client().login('runner', 'wrong')

    client = strict_server.client()
    client.login('runner', 'right')

    assert client.get('/workflows')[0] == 200



def test_admin_unblocks_a_user(strict_server):

    for _ in range(2):
        strict_server.client().login('runner', 'wrong')

    admin = strict_server.client()
    admin.login('boss', 'right')

    _, _, page = admin.get('/settings', headers={'Accept': 'text/html'})
    assert 'data-action="unblock-login" data-user="runner"' in page

    stranger = strict_server.client()
    stranger.login('stranger', 'right')
    assert stranger.post('/api/unblock_login/runner')[0] == 403

    assert admin.post('/api/unblock_login/runner')[0] == 200
    assert admin.post('/api/unblock_login/runner')[0] == 404

    # In the audit log (docs/features/audit-log.md)
    import sqlite3
    with sqlite3.connect(os.path.join(strict_server.directory, 'var', 'app.sqlite')) as conn:
        assert conn.execute("SELECT user, object FROM audit_log WHERE event = 'login_unblocked'").fetchall() == [('boss', 'runner')]

    client = strict_server.client()
    client.login('runner', 'right')
    assert client.get('/workflows')[0] == 200



def test_logins_which_are_not_tried_do_not_block_the_user(strict_server):

    for _ in range(3):
        strict_server.client().login('runner', 'ab\x01c')

    client = strict_server.client()
    client.login('runner', 'right')

    assert client.get('/workflows')[0] == 200



def test_warning_if_failures_can_disable_profiles(server):

    assert 'C_LOGIN_MAX_FAILURES = 3: failed logins in i-Releaser can disable IBM i profiles' in server.read_logs()



#---------------------------------------------------------
# blocking-login-in-middleware (review 2026-11-23)
#---------------------------------------------------------

def test_hanging_sign_on_does_not_block_other_requests(strict_server):

    result = {}

    def slow_login():
        result['status'] = strict_server.client().request('POST', '/login', form={'user': 'runner', 'password': 'slow'}, headers={'Accept': 'text/html'})

    thread = threading.Thread(target=slow_login)
    thread.start()
    wait_until(lambda: is_signing_on(strict_server), what='the slow sign-on has started')

    start = time.time()
    assert strict_server.client().get('/login', headers={'Accept': 'text/html'})[0] == 200
    assert time.time() - start < 1

    thread.join()
    status, _, text = result['status']
    # Ended by the timeout, with the normal message
    assert status == 200
    assert 'Login failed. Check your user' in text



def test_too_many_logins_at_the_same_time(strict_server):

    thread = threading.Thread(target=lambda: strict_server.client().request('POST', '/login', form={'user': 'runner', 'password': 'slow'}))
    thread.start()
    wait_until(lambda: is_signing_on(strict_server), what='the slow sign-on has started')

    status, _, _ = strict_server.client().request('POST', '/login', form={'user': 'boss', 'password': 'right'})

    thread.join()
    assert status == 503



def test_sign_on_without_answer_does_not_block_the_user(strict_server):

    for _ in range(2):
        strict_server.client().request('POST', '/login', form={'user': 'runner', 'password': 'slow'})

    client = strict_server.client()
    client.login('runner', 'right')
    assert client.get('/workflows')[0] == 200
