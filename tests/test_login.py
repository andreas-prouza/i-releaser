"""The login with the password check: pyodbc is replaced by a stub which records the connection strings"""
import json, os

import pytest

from web_server import Web_Server


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
    return server.odbc_log.read_text().splitlines()



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
    _, _, text = client.request('POST', '/', form={'user': 'boss', 'password': 'right'}, headers={'Accept': 'text/html'})

    assert 'Too many failed logins' in text
    assert len(get_connections(server)) == 3



def test_error_does_not_tell_what_was_wrong(server):

    _, _, wrong_password = server.client().request('POST', '/', form={'user': 'boss', 'password': 'wrong'}, headers={'Accept': 'text/html'})
    _, _, unknown_user = server.client().request('POST', '/', form={'user': 'unknown', 'password': 'wrong'}, headers={'Accept': 'text/html'})

    message = 'Login failed. Check your user and password'

    assert message in wrong_password
    assert message in unknown_user
    assert 'Connection refused' not in wrong_password
