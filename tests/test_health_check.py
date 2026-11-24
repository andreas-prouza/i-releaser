"""Health check (docs/features/health-check.md)"""
import json, os, sqlite3

import pytest

from web_server import Web_Server


@pytest.fixture(scope='module')
def server():
    s = Web_Server().start()
    yield s
    s.close()


def test_without_login_only_the_status(server):

    status, headers, text = server.client().get('/healthz')

    assert status == 200
    body = json.loads(text)
    assert body == {'status': 'ok', 'checks': {'database': 'ok', 'processing_service': 'ok', 'disk_space': 'ok'}}
    assert 'set-cookie' not in headers


def test_with_login_also_the_version(server):

    body = json.loads(server.client('boss').get('/healthz')[2])

    assert body['status'] == 'ok' and 'version' in body


def test_processing_service_not_running(server):

    boss = server.client('boss')
    assert boss.post_json('/api/set_processing_mode/service')[0] == 200
    try:
        status, _, text = server.client().get('/healthz')
        assert status == 503
        assert json.loads(text)['checks']['processing_service'] == 'error'
        assert 'not running' in json.loads(boss.get('/healthz')[2])['details']['processing_service']
    finally:
        boss.post_json('/api/set_processing_mode/thread')


def test_not_in_the_access_log(server):

    server.client().get('/healthz')

    assert 'GET /healthz' not in server.read_logs()


def test_database_which_can_not_be_read():

    server = Web_Server().start()
    try:
        with sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite')) as conn:
            conn.execute("PRAGMA user_version = 1")

        status, _, text = server.client().get('/healthz')
        assert status == 503
        assert json.loads(text)['checks']['database'] == 'error'
    finally:
        server.close()
