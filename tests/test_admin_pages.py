"""The admin pages (docs/features/web-ui-admin-pages.md): settings, processing, logs, workflows, the own account"""
import datetime, html, json, os, re

import pytest

from web_server import USERS, Web_Server


HTML = {'Accept': 'text/html'}
ROLES = {'releaser': {'permissions': {'general': [], 'workflows': {'par_wf': {'general': ['read'], 'stages': {'A': ['run']}}}}}}


@pytest.fixture(scope='module')
def server():
    users = {**USERS, 'runner': {**USERS['runner'], 'roles': ['releaser']}}
    s = Web_Server(users=users)
    with open(s.path('etc', 'user_permissions.json'), 'w') as f:
        json.dump({'users': users, 'roles': ROLES}, f)
    s.start()
    yield s
    s.stop_service()
    s.close()


@pytest.fixture()
def boss(server):
    return server.client('boss')


@pytest.fixture(scope='module')
def log(server):
    return sorted(os.listdir(os.path.join(server.web_dir, 'log')))[0]


def page(client, path: str) -> tuple[int, str]:
    status, _, text = client.get(path, headers=HTML)
    return status, text


def title_and_entry(text: str) -> tuple[str, str]:
    title = re.search(r'<title>(.*?)</title>', text, re.S).group(1).strip()
    entry = re.search(r'<(?:a|button)\b[^>]*class="app-nav-link active"[^>]*?data-nav="([^"]+)"', text)
    return html.unescape(title), entry.group(1) if entry else None



def test_admin_pages_need_admin(server, log):

    intern = server.client('intern')
    for path in ['/settings', '/settings/processing', '/settings/permissions', '/settings/security', '/settings/audit', '/settings/configuration', f"/log/{log}", f"/log/{log}/download"]:
        assert page(intern, path)[0] == 403, path



def test_titles_and_active_entries(server, boss, log):

    expected = {
        '/settings': ('System · Administration · i-Releaser', 'settings'),
        '/settings/processing': ('Processing · Administration · i-Releaser', 'settings'),
        '/settings/security': ('Security · Administration · i-Releaser', 'settings'),
        '/settings/configuration': ('Settings · Administration · i-Releaser', 'settings'),
        '/settings/permissions': ('Permissions · Administration · i-Releaser', 'settings'),
        f"/log/{log}": (f"{log} · Logs · i-Releaser", 'logs'),
        '/workflows': ('Workflows · i-Releaser', 'workflows'),
        '/user': ('My account · i-Releaser', 'user'),
    }
    for path, (title, entry) in expected.items():
        status, text = page(boss, path)
        assert status == 200, path
        assert title_and_entry(text) == (title, entry), path



def test_settings_page(server, boss):

    _, text = page(boss, '/settings')
    assert '????' not in text and 'Web port' not in text
    assert 'Version' in text and 'Database' in text
    assert '<a class="nav-link active" href="/settings" aria-current="page">System</a>' in text



def test_security_has_its_own_tab(server, boss):
    """Tokens, two-factor authentication and blocked logins: Security, not System (docs/features/web-ui-admin-pages.md#decisions-2026-11-24)"""

    sections = ['id="tokens-title"', 'id="two-factor-title"', 'id="blocked-title"']

    _, system = page(boss, '/settings')
    _, security = page(boss, '/settings/security')

    assert all(section in security for section in sections)
    assert not any(section in system for section in sections)
    assert 'id="retention-title"' in system and 'id="retention-title"' not in security
    assert '<a class="nav-link active" href="/settings/security" aria-current="page">Security</a>' in security
    assert 'pages/security.js' in security and 'pages/settings.js' not in security



def test_permissions_have_no_entry_of_their_own(server, boss):
    """The permissions are a tab of the administration: the navigation marks Administration"""

    _, text = page(boss, '/settings/permissions')
    assert title_and_entry(text)[1] == 'settings'
    assert 'data-nav="permissions"' not in text
    assert '<a class="nav-link active" href="/settings/permissions" aria-current="page">Permissions</a>' in text



def start_time(text: str, label: str) -> datetime.datetime:
    """A start time of the general settings (docs/features/start-times.md): UTC, shown by the browser in its time zone"""

    match = re.search(rf'<dt>{label}</dt>\s*<dd><time datetime="([^"]+)" data-local-time>', text)
    assert match, f"{label} not found"
    return datetime.datetime.fromisoformat(match.group(1))



def test_settings_show_the_start_of_the_web_app(server, boss):

    server.stop_service()
    server.wait_for_service(running=False)

    _, text = page(boss, '/settings')
    now = datetime.datetime.now(datetime.timezone.utc)
    assert now - datetime.timedelta(minutes=10) < start_time(text, 'Web app started') <= now
    assert re.search(r'<dt>Processing service started</dt>\s*<dd>Not running</dd>', text)



def test_start_of_the_running_processing_service(server, boss):

    assert boss.post_json('/api/processing_service/start')[0] == 200
    pid = server.wait_for_service()
    try:
        _, text = page(boss, '/settings/processing')
        match = re.search(r'id="service-started">Started <time datetime="([^"]+)" data-local-time>[^<]+</time> · process (\d+)</p>', text)
        assert match, "start of the service not found"
        start = datetime.datetime.fromisoformat(match.group(1))
        now = datetime.datetime.now(datetime.timezone.utc)
        assert now - datetime.timedelta(minutes=2) < start <= now
        assert int(match.group(2)) == pid

        _, text = page(boss, '/settings')
        assert start_time(text, 'Processing service started') == start
        assert f'<span class="ir-reason">process {pid}</span>' in text
    finally:
        boss.post_json('/api/processing_service/stop')
        server.wait_for_service(running=False)

    _, text = page(boss, '/settings/processing')
    assert 'id="service-started"' not in text



def test_jobs_show_the_stage_and_a_duration(server, boss):

    assert boss.post_json('/api/set_processing_mode/service')[0] == 200
    assert boss.post_json('/api/processing_service/start')[0] == 200
    server.wait_for_service()

    deployment = boss.create_deployment('hidden_wf')
    try:
        assert boss.run_stage(deployment, 'START')[0] == 200
        boss.wait_for_stage(deployment, 'START', timeout=30)

        _, text = page(boss, '/settings/processing')
        jobs = json.loads(html.unescape(re.search(r'id="jobs-data">(.*?)</script>', text, re.S).group(1)))
        job = [j for j in jobs if j['meta_file_id'] == deployment][0]
        assert job['stage'] == 'START'
        assert job['deployment'] == 'hidden 1'
        assert job['status'] == 'finished'
        assert re.fullmatch(r'\d+(\.\d)? s|\d+ min( \d+ s)?', job['duration']), job['duration']
        assert 'data-service="running"' in text
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")
        boss.post_json('/api/processing_service/stop')
        boss.post_json('/api/set_processing_mode/thread')



def test_log_page_keeps_the_level_of_the_url(server, boss, log):

    _, text = page(boss, f"/log/{log}/500?level=WARNING&q=start")
    assert re.findall(r'<option value="(\d+)"\s*selected', text) == ['500']
    assert '<option value="WARNING" selected>' in text
    assert 'value="start"' in text
    # Each line with its level, for the filter of the page
    assert re.search(r'<span class="ir-log-line lvl-\w+" data-level="(DEBUG|INFO|WARNING|ERROR|CRITICAL)">', text)

    # An unknown value: the default
    _, text = page(boss, f"/log/{log}/7?level=nope")
    assert re.findall(r'<option value="(\d+)"\s*selected', text) == ['100']
    assert '<option value="all" selected>' in text



def test_download_of_a_log(server, boss, log):

    status, headers, text = boss.get(f"/log/{log}/download")
    assert status == 200
    assert 'attachment' in headers['content-disposition'] and log in headers['content-disposition']
    with open(os.path.join(server.web_dir, 'log', log), encoding='utf-8', errors='replace') as f:
        assert text[:200] == f.read()[:200]

    assert boss.get('/log/nope.log/download')[0] == 404



def test_workflows_page(server, boss):

    # stranger may only read seq_wf
    _, text = page(server.client('stranger'), '/workflows')
    assert re.findall(r'<section class="ir-card ir-workflow"[^>]*data-workflow="([^"]+)"', text) == ['seq_wf']
    assert 'data-action="start-workflow"' not in text
    assert 'Invalid workflow files' not in text

    _, text = page(boss, '/workflows')
    names = re.findall(r'<section class="ir-card ir-workflow"[^>]*data-workflow="([^"]+)"', text)
    assert set(names) == {'seq_wf', 'par_wf', 'slow_wf', 'hidden_wf'}
    # The stages as flow, without status
    par = text[text.index('data-workflow="par_wf"'):]
    par = par[:par.index('</section>')]
    assert re.findall(r'<div class="ir-flow-node static[^"]*"[^>]*data-stage="([^"]+)"', par) == ['START', 'A', 'B', 'END']
    assert 'parallel stages' in par and 'parallel deployments' in par
    assert 'data-action="select-stage"' not in text
    # Markers of the arrows: unique per flow
    assert len(re.findall(r'<marker id="([^"]+)"', text)) == len(set(re.findall(r'<marker id="([^"]+)"', text)))



def test_user_page_shows_roles_and_permissions(server):

    _, text = page(server.client('runner'), '/user')
    assert 'roles: releaser' in text

    rows = dict(re.findall(r'<th scope="row" class="ir-perm-level-\d">([^<]+)</th>\s*<td>(.*?)</td>', text, re.S))
    assert 'run' in rows['seq_wf'] and 'inherited' not in rows['seq_wf'].split('run')[0][-60:]
    # From the role: par_wf (read) and its stage A (run)
    assert 'title="From General, role releaser">read' in rows['par_wf']
    assert 'title="From role releaser">run' in rows['A']
