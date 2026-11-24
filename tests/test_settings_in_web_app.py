"""Settings changed in the web app: pages, API, other processes (docs/features/settings-in-web-app.md). The module: test_web_settings.py"""
import html
import json
import os
import re
import sqlite3

import pytest

from web_server import Web_Server


HTML = {'Accept': 'text/html'}


@pytest.fixture(scope='module')
def server():
    s = Web_Server().start()
    yield s
    s.stop_service()
    s.close()


@pytest.fixture()
def boss(server):
    return server.client('boss')


def app_json(server) -> dict:
    path = server.path('etc', 'app.json')
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def audit_entries(server, name: str) -> list[dict]:
    conn = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'))
    conn.row_factory = sqlite3.Row
    with conn:
        rows = conn.execute("SELECT * FROM audit_log WHERE event = 'setting_changed' AND object = ? ORDER BY id", (name,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def row_of(page: str, name: str) -> str:
    match = re.search(rf'<tr data-setting="{name}".*?</tr>', page, re.S)
    assert match, f"{name} not on the page"
    return match.group(0)



def test_page_shows_the_settings_of_the_web_app_and_the_others(server, boss):

    assert server.client('intern').get('/settings/configuration', headers=HTML)[0] == 403

    status, _, page = boss.get('/settings/configuration', headers=HTML)
    assert status == 200
    assert '<a class="nav-link active" href="/settings/configuration" aria-current="page">Settings</a>' in page

    # Editable, with its default
    row = row_of(page, 'C_MAX_PARALLEL_STEPS')
    assert 'data-action="save-setting"' in row and 'data-kind="int"' in row
    # Only shown
    assert 'data-action' not in row_of(page, 'C_APP_DB_FILE')
    # The security ones are on their own tab, not changeable
    assert 'data-setting="C_2FA_POLICY"' not in page
    _, _, security = boss.get('/settings/security', headers=HTML)
    assert 'data-action' not in row_of(security, 'C_2FA_POLICY')



def test_processing_mode_is_shown_as_it_counts(server, boss):
    """Changed on the tab Processing (etc/app.json): the same value and source as there"""

    assert boss.post_json('/api/set_processing_mode/service')[0] == 200
    try:
        _, _, page = boss.get('/settings/configuration', headers=HTML)
        row = row_of(page, 'C_PROCESSING_MODE')
        assert '<td class="ir-mono">service</td>' in row and '>web app<' in row
    finally:
        assert boss.post_json('/api/set_processing_mode/thread')[0] == 200



def test_change_counts_at_once_and_is_audited(server, boss):

    try:
        status, body = boss.post_json('/api/settings/C_HEALTH_MIN_FREE_MB', {'value': 10 ** 9})
        assert status == 200, body
        assert app_json(server)['C_HEALTH_MIN_FREE_MB'] == 10 ** 9

        # The health check of the web app uses it without restart
        status, _, text = boss.get('/healthz')
        assert status == 503 and json.loads(text)['checks']['disk_space'] == 'error'

        _, _, page = boss.get('/settings/configuration', headers=HTML)
        row = row_of(page, 'C_HEALTH_MIN_FREE_MB')
        assert f'value="{10 ** 9}"' in row and '>web app<' in row and 'data-action="reset-setting"' in row

        entry = audit_entries(server, 'C_HEALTH_MIN_FREE_MB')[-1]
        assert entry['user'] == 'boss' and json.loads(entry['details'])['new'] == 10 ** 9
    finally:
        status, body = boss.request('DELETE', '/api/settings/C_HEALTH_MIN_FREE_MB')[:2]

    assert status == 200, body
    assert 'C_HEALTH_MIN_FREE_MB' not in app_json(server)
    assert boss.get('/healthz')[0] == 200
    assert json.loads(audit_entries(server, 'C_HEALTH_MIN_FREE_MB')[-1]['details'])['reset'] is True



@pytest.mark.parametrize('name, value', [('C_HEALTH_MIN_FREE_MB', -5), ('C_HEALTH_MIN_FREE_MB', 'much'), ('C_2FA_POLICY', 'off'),
                                         ('C_LOGIN_MAX_FAILURES', 100), ('C_APP_DB_FILE', '/tmp/x.sqlite')])
def test_refused_changes(server, boss, name, value):

    before = app_json(server)
    status, body = boss.post_json(f"/api/settings/{name}", {'value': value})
    assert status == 422, body
    assert app_json(server) == before

    assert boss.request('DELETE', f"/api/settings/{name}")[0] == (422 if name in ('C_2FA_POLICY', 'C_LOGIN_MAX_FAILURES', 'C_APP_DB_FILE') else 200)



def test_only_admins_change_settings(server):

    intern = server.client('intern')
    assert intern.post_json('/api/settings/C_HEALTH_MIN_FREE_MB', {'value': 1})[0] == 403
    assert intern.request('DELETE', '/api/settings/C_HEALTH_MIN_FREE_MB')[0] == 403
    assert 'C_HEALTH_MIN_FREE_MB' not in app_json(server)



def test_running_processing_service_uses_a_change(server, boss):
    """Changed after the start of the service: its next job has the new step timeout (the step sleeps 2 seconds)"""

    assert boss.post_json('/api/set_processing_mode/service')[0] == 200
    assert boss.post_json('/api/processing_service/start')[0] == 200
    server.wait_for_service()

    deployment = boss.create_deployment('slow_wf')
    try:
        assert boss.post_json('/api/settings/C_COMMAND_TIMEOUT_SECONDS', {'value': 1})[0] == 200

        assert boss.run_stage(deployment, 'START')[0] == 200
        stage = boss.wait_for_stage(deployment, 'START', timeout=30)
        assert stage['status'] == 'failed'

        _, _, text = boss.post(f"/api/get_meta_file_json/{deployment}")
        assert re.search(r'time ?out|timed out', html.unescape(text), re.I), text[:2000]
    finally:
        boss.request('DELETE', '/api/settings/C_COMMAND_TIMEOUT_SECONDS')
        boss.post(f"/api/cancel_deployment/{deployment}")
        boss.post_json('/api/processing_service/stop')
        server.wait_for_service(running=False)
        boss.post_json('/api/set_processing_mode/thread')
