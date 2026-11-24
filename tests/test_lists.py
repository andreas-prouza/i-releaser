"""The lists of the web app (docs/features/web-ui-lists.md): deployments of a project, objects, start of a workflow"""
import html, json, os, re, sqlite3, time

import pytest

from web_server import WORKFLOWS, Web_Server


HTML = {'Accept': 'text/html'}


def step(name, cmd):
    return {'processing_step': name, 'environment': 'PASE', 'execute': cmd, 'check_error': True}


def simple(name: str, project: str, command: str = 'echo quick', **extra) -> dict:
    return {'name': name, 'default_project': project, 'step_action': [step('only', command)], **extra,
            'stages': [{'name': 'START', 'next_stages': ['PROD'], 'host': 'localhost', 'processing_steps': ['only']},
                       {'name': 'PROD', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': ['only']},
                       {'name': 'END'}]}


LIST_WORKFLOWS = {
    **WORKFLOWS,
    'failing_wf': simple('failing_wf', 'failing', 'ls /does/not/exist'),
    'sleeping_wf': simple('sleeping_wf', 'sleeping', 'sleep 3'),
    'queue_wf': simple('queue_wf', 'queue'),
    'fields_wf': simple('fields_wf', 'fields', create_fields=['$.ticket', '$.jira.issue']),
}


@pytest.fixture(scope='module')
def server():
    s = Web_Server(workflows=LIST_WORKFLOWS).start()
    yield s
    s.close()


@pytest.fixture()
def boss(server):
    return server.client('boss')


def rows_of(text: str) -> list[dict]:
    return json.loads(html.unescape(re.search(r'<script type="application/json" id="deployments-data">(.*?)</script>', text, re.S).group(1)))


def tabs_of(text: str) -> dict:
    """Project -> number of open deployments (0 without a number)"""
    tabs = {}
    for name, rest in re.findall(r'<a class="nav-link[^"]*" href="/project/[^"]+"[^>]*>\s*([^<\s]+)(.*?)</a>', text, re.S):
        found = re.search(r'title="Open deployments">(\d+)', rest)
        tabs[name] = int(found.group(1)) if found else 0
    return tabs


def list_page(client, path: str) -> tuple[int, str]:
    status, headers, text = client.get(path, headers=HTML)
    return status, text



#-----------------------------------------------------------------------------------------------
# Deployments
#-----------------------------------------------------------------------------------------------

def test_project_in_the_url(server, boss):

    deployment = boss.create_deployment('par_wf')
    try:
        status, text = list_page(boss, '/project/par')
        assert status == 200
        assert 'Project par' in text
        assert [row['id'] for row in rows_of(text)] == [deployment]
        assert re.search(r'<a class="nav-link active" href="/project/par" aria-current="page">', text)

        # `/` shows the project used last
        assert 'Project par' in list_page(boss, '/')[1]

        # An unknown project: the project of `/`, nothing is stored
        status, text = list_page(boss, '/project/unknown')
        assert status == 200 and 'Project par' in text
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_only_readable_projects_and_deployments(server, boss):

    hidden = boss.create_deployment('hidden_wf')
    try:
        _, text = list_page(server.client('stranger'), '/project/hidden')
        # stranger may only read seq_wf
        assert set(tabs_of(text)) == {'seq'}
        assert rows_of(text) == [] or all(row['workflow'] == 'seq_wf' for row in rows_of(text))
        assert f'"id": {hidden}' not in text

        _, text = list_page(boss, '/project/hidden')
        assert hidden in [row['id'] for row in rows_of(text)]
    finally:
        boss.post(f"/api/cancel_deployment/{hidden}")



def wait_status(client, deployment: int, stage: str, status: str, timeout: float = 10) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if client.get_stages(deployment)[stage]['status'] == status:
            return
        time.sleep(0.1)
    raise AssertionError(f"{stage} not {status}")


def stage_of(client, project: str, deployment: int) -> tuple:
    row = [row for row in rows_of(list_page(client, f"/project/{project}")[1]) if row['id'] == deployment][0]
    return row['stage'], (row['stage_view'] or {}).get('text')



def test_stage_column(server, boss):

    ready = boss.create_deployment('seq_wf')
    failed = boss.create_deployment('failing_wf')
    running = boss.create_deployment('sleeping_wf')
    parallel = boss.create_deployment('par_wf')
    queued = boss.create_deployment('queue_wf')
    finished = boss.create_deployment('hidden_wf')

    try:
        assert stage_of(boss, 'seq', ready) == ('START', 'ready')

        boss.run_stage(failed, 'START')
        boss.wait_for_stage(failed, 'START')
        assert stage_of(boss, 'failing', failed) == ('START', 'failed')

        boss.run_stage(running, 'START')
        wait_status(boss, running, 'START', 'in process')
        assert stage_of(boss, 'sleeping', running) == ('START', 'in process')

        # Parallel stages: the first one
        boss.run_stage(parallel, 'START')
        boss.wait_for_stage(parallel, 'START')
        assert stage_of(boss, 'par', parallel) == ('A', 'ready')

        assert boss.post_json('/api/set_processing_mode/service')[0] == 200
        assert boss.run_stage(queued, 'START')[0] == 200
        assert stage_of(boss, 'queue', queued) == ('START', 'queued')

        boss.post(f"/api/cancel_deployment/{queued}")
        assert boss.post_json('/api/set_processing_mode/thread')[0] == 200
        assert stage_of(boss, 'queue', queued) == ('–', None)

        boss.finish_deployment(finished, stages=('START',))
        assert boss.get_deployment(finished)['general']['status'] == 'finished'
        assert stage_of(boss, 'hidden', finished) == ('–', None)

        boss.wait_for_stage(running, 'START', timeout=20)
    finally:
        boss.post_json('/api/set_processing_mode/thread')
        for deployment in [ready, failed, running, parallel, queued, finished]:
            boss.post(f"/api/cancel_deployment/{deployment}")



def test_number_of_open_deployments(server, boss):

    first = boss.create_deployment('fields_wf')
    second = boss.create_deployment('fields_wf')
    try:
        assert tabs_of(list_page(boss, '/')[1])['fields'] == 2
        boss.post(f"/api/cancel_deployment/{second}")
        assert tabs_of(list_page(boss, '/')[1])['fields'] == 1
    finally:
        boss.post(f"/api/cancel_deployment/{first}")
        boss.post(f"/api/cancel_deployment/{second}")
    assert tabs_of(list_page(boss, '/')[1])['fields'] == 0



def test_list_has_no_database_names_and_no_none(server, boss):

    deployment = boss.create_deployment('seq_wf')
    try:
        _, text = list_page(boss, '/project/seq')
        visible = re.sub(r'<script.*?</script>', '', text, flags=re.S)
        for name in ['meta_file_id', 'create_time', 'update_time', 'workflow_name', 'Workflows <code>']:
            assert name not in visible, name
        assert 'None' not in json.dumps(rows_of(text))
        assert 'None' not in re.sub(r'<[^>]+>', '', visible)
        # Columns: their titles in the script of the page
        with open(os.path.join(server.web_dir, 'static', 'assets', 'js', 'pages', 'deployments.js')) as f:
            script = f.read()
        assert [title for title in re.findall(r"title: '([^']+)'", script)] == ['Version', 'Status', 'Workflow', 'Stage', 'Created', 'Last update', 'Id']
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_start_workflow_only_with_the_permission(server):

    users = {'boss': True, 'intern': True, 'runner': False, 'stranger': False}
    for user, allowed in users.items():
        _, text = list_page(server.client(user), '/project/seq')
        assert ('data-action="start-workflow"' in text) == allowed, user
        startable = json.loads(html.unescape(re.search(r'id="start-workflows">(.*?)</script>', text, re.S).group(1)))
        assert ([wf['name'] for wf in startable] == ['seq_wf']) == allowed, user

    _, text = list_page(server.client('boss'), '/project/fields')
    startable = json.loads(html.unescape(re.search(r'id="start-workflows">(.*?)</script>', text, re.S).group(1)))
    assert startable == [{'name': 'fields_wf', 'project': 'fields', 'fields': [
        {'path': '$.ticket', 'keys': ['ticket'], 'label': 'ticket'}, {'path': '$.jira.issue', 'keys': ['jira', 'issue'], 'label': 'jira.issue'}]}]

    # The page Workflows: `Start` only for workflows which may be started
    _, text = list_page(server.client('runner'), '/workflows')
    assert 'data-action="start-workflow"' not in text



#-----------------------------------------------------------------------------------------------
# Objects
#-----------------------------------------------------------------------------------------------

def insert_objects(server, deployment: int, objects: list[tuple]) -> None:
    db = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'), timeout=10)
    db.executemany("""INSERT INTO deploy_objects (meta_file_id, level, prod_lib, lib, name, type, attribute, deploy_status, ready, properties)
                      VALUES (?, 1, ?, 'devlib', ?, ?, 'rpgle', 'new', 1, '{}')""", [(deployment, *o) for o in objects])
    db.commit()
    db.close()


def objects(client, **params) -> dict:
    from urllib.parse import urlencode
    status, _, text = client.get(f"/api/deploy_objects?{urlencode(params)}")
    assert status == 200, text
    return json.loads(text)


@pytest.fixture(scope='module')
def many_objects(server):
    boss = server.client('boss')
    old = boss.create_deployment('seq_wf')
    insert_objects(server, old, [('oldlib', 'ancient', 'pgm')])
    new = boss.create_deployment('hidden_wf')
    # Newer than the old one: 1,100 objects, so `ancient` is not among the newest 1,000
    insert_objects(server, new, [('prodlib', f"obj{i:04}", 'pgm' if i % 2 else 'file') for i in range(1100)])
    yield {'old': old, 'new': new}
    boss.post(f"/api/cancel_deployment/{old}")
    boss.post(f"/api/cancel_deployment/{new}")



def test_deploy_objects(server, boss, many_objects):

    page = objects(boss, limit=25)
    assert page['total'] == 1101
    assert len(page['rows']) == 25
    assert set(page['rows'][0]) == {'project', 'prod_lib', 'name', 'type', 'attribute', 'last_deployment', 'deployments'}

    # Not among the newest 1,000, found by the search
    assert [row['name'] for row in objects(boss, search='ancient')['rows']] == ['ancient']

    # Filters: project, type (exact), name (part)
    assert objects(boss, filter=json.dumps({'project': 'seq'}))['total'] == 1
    assert objects(boss, filter=json.dumps({'project': 'hidden', 'type': 'file'}))['total'] == 550
    assert objects(boss, filter=json.dumps({'name': 'obj10'}))['total'] == 100

    # Sort, offset and limit
    names = [row['name'] for row in objects(boss, sort='name', order='asc', offset=2, limit=3)['rows']]
    assert names == ['obj0001', 'obj0002', 'obj0003']
    assert objects(boss, sort='name', order='desc', limit=1)['rows'][0]['name'] == 'obj1099'

    # Values which are not allowed
    assert boss.get('/api/deploy_objects?filter=nojson')[0] == 422
    assert objects(boss, sort='name; DROP TABLE x', limit=1)['total'] == 1101
    assert objects(boss, filter=json.dumps({'1=1) OR (1': 'x'}))['total'] == 1101
    assert len(objects(boss, limit=100000)['rows']) == 500

    # % and _ in a search are characters, not patterns
    assert objects(boss, search='%')['total'] == 0



def test_deploy_objects_of_readable_workflows_only(server, many_objects):

    # stranger may read seq_wf only
    page = objects(server.client('stranger'), limit=50)
    assert page['total'] == 1
    assert page['rows'][0]['name'] == 'ancient'

    # The history of an object of hidden_wf: empty for stranger
    from urllib.parse import urlencode
    query = urlencode({'project': 'hidden', 'prod_lib': 'prodlib', 'name': 'obj0001', 'type': 'pgm', 'attribute': 'rpgle'})
    _, _, history = server.client('stranger').get(f"/list-objects/history?{query}", headers=HTML)
    assert 'No deployment of this object which you may see' in history
    _, _, history = server.client('boss').get(f"/list-objects/history?{query}", headers=HTML)
    assert f'/show_details/{many_objects["new"]}' in history

    # The values of the filters
    _, _, page = server.client('stranger').get('/list-objects', headers=HTML)
    filters = json.loads(html.unescape(re.search(r'id="object-filters">(.*?)</script>', page, re.S).group(1)))
    assert filters['project'] == ['seq']
