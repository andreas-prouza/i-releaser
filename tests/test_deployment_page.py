"""The deployment page (docs/features/web-ui-deployment-page.md): flow, attention bar, steps, permissions, objects"""
import html, importlib.util, json, os, re, time

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

from web_server import ROOT_DIR, USERS, WORKFLOWS, Web_Server


WEB_DIR = os.path.join(ROOT_DIR, 'webapp')
HTML = {'Accept': 'text/html'}


def load_web_module(name: str):
    """Modules of webapp/web_modules which don't need the web app"""
    spec = importlib.util.spec_from_file_location(name, os.path.join(WEB_DIR, 'web_modules', f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage_flow = load_web_module('stage_flow')
status_view = load_web_module('status_view')
template_filters = load_web_module('template_filters')



#-----------------------------------------------------------------------------------------------
# Layout of the flow (web_modules/stage_flow.py)
#-----------------------------------------------------------------------------------------------

def stage(name: str, next: list|None=None, status: str='new') -> dict:
    return {'id': hash(name) % 10000, 'name': name, 'next': next or [], 'status': status}


def positions(layout) -> dict:
    return {node['name']: (node['col'], node['row']) for node in layout.nodes}


def segments(d: str) -> list:
    points = [tuple(map(float, p.split())) for p in d[2:].split(' L ')]
    return list(zip(points, points[1:], strict=False))


def node_box(node) -> tuple:
    """The part of a cell a line must not cross: circle, name and status"""
    left = stage_flow.cell_left(node['col']) + 4
    top = node['row'] * (stage_flow.ROW_HEIGHT + stage_flow.ROW_GAP)
    return left, top, left + stage_flow.COL_WIDTH - 8, top + stage_flow.ROW_HEIGHT


def crosses(segment, box) -> bool:
    (x1, y1), (x2, y2) = segment
    left, top, right, bottom = box
    if y1 == y2:
        return top < y1 < bottom and min(x1, x2) < right and max(x1, x2) > left
    return left < x1 < right and min(y1, y2) < bottom and max(y1, y2) > top


def crossed_stages(layout) -> list:
    """Stages a connection runs across (other than its own two stages)"""

    nodes = {node['name']: node for node in layout.nodes}
    found = []
    for line in layout.connections:
        for name, node in nodes.items():
            if name in (line['source'], line['target']):
                continue
            # The last piece ends at its stage; the circle of the stage before it is left of it
            if any(crosses(segment, node_box(node)) for segment in segments(line['d'])):
                found.append((line['source'], line['target'], name))
    return found



def test_flow_of_a_sequence():

    layout = stage_flow.get_layout([stage('START', ['A']), stage('A', ['END']), stage('END')])

    assert positions(layout) == {'START': (0, 0), 'A': (1, 0), 'END': (2, 0)}
    assert (layout.columns, layout.rows) == (3, 1)
    assert [(c['kind'], c['source'], c['target']) for c in layout.connections] == [
        ('out', 'START', 'A'), ('in', None, 'A'), ('out', 'A', 'END'), ('in', None, 'END')]
    assert [node['number'] for node in layout.nodes] == [1, 2, 3]
    assert crossed_stages(layout) == []



def test_flow_of_parallel_branches_which_join():
    """etc/examples/workflows/parallel_example.json and test_wf"""

    with open(os.path.join(ROOT_DIR, 'etc', 'examples', 'workflows', 'parallel_example.json')) as f:
        workflow = json.load(f)

    layout = stage_flow.get_layout([stage(s['name'], s.get('next_stages')) for s in workflow['stages']])

    assert positions(layout) == {'START': (0, 0), 'STAGE 2.1': (1, 0), 'STAGE 2.2': (1, 1), 'STAGE 3': (2, 0), 'END': (3, 0)}
    # One last piece into the stage which waits for both
    assert len([c for c in layout.connections if c['kind'] == 'in' and c['target'] == 'STAGE 3']) == 1
    assert len([c for c in layout.connections if c['kind'] == 'out' and c['target'] == 'STAGE 3']) == 2
    assert crossed_stages(layout) == []



def test_flow_has_each_stage_once():

    layout = stage_flow.get_layout([stage('START', ['A', 'B']), stage('A', ['C']), stage('B', ['C']), stage('C', ['END']), stage('END')])

    assert [node['name'] for node in layout.nodes].count('C') == 1
    assert positions(layout)['C'] == (2, 0)
    assert crossed_stages(layout) == []



def test_flow_with_a_connection_back_to_an_earlier_stage():

    layout = stage_flow.get_layout([stage('START', ['A']), stage('A', ['B']), stage('B', ['A', 'END']), stage('END')])

    assert positions(layout) == {'START': (0, 0), 'A': (1, 0), 'B': (2, 0), 'END': (3, 0)}
    back = [c for c in layout.connections if c['back']]
    assert [(c['source'], c['target']) for c in back] == [('B', 'A')]
    # In a row of its own below the stages
    assert layout.rows == 2
    assert crossed_stages(layout) == []



def test_flow_without_next_stages():

    layout = stage_flow.get_layout([stage('START')])
    assert positions(layout) == {'START': (0, 0)}
    assert layout.connections == []

    assert stage_flow.get_layout([]).nodes == []

    # Without START: the first stage, and stages which can't be reached are shown too
    layout = stage_flow.get_layout([stage('BEGIN', ['X']), stage('X'), stage('LOST')])
    assert positions(layout) == {'BEGIN': (0, 0), 'X': (1, 0), 'LOST': (0, 1)}

    # A next stage which doesn't exist is left out
    assert stage_flow.get_layout([stage('START', ['MISSING'])]).connections == []



def test_flow_with_branches_of_different_length():
    """The connection which skips columns runs in a free row, not across a stage"""

    layout = stage_flow.get_layout([stage('START', ['A', 'END']), stage('A', ['B']), stage('B', ['END']), stage('END')])

    assert positions(layout) == {'START': (0, 0), 'A': (1, 0), 'B': (2, 0), 'END': (3, 0)}
    assert crossed_stages(layout) == []
    assert layout.rows == 2

    # The same, the short branch first
    layout = stage_flow.get_layout([stage('START', ['END', 'A']), stage('A', ['B']), stage('B', ['END']), stage('END')])
    assert crossed_stages(layout) == []



def test_colours_of_the_lines_of_a_join():

    def lines(status_21, status_22):
        layout = stage_flow.get_layout([stage('START', ['2.1', '2.2'], 'finished'), stage('2.1', ['3'], status_21), stage('2.2', ['3'], status_22), stage('3', ['END']), stage('END')])
        return {(c['kind'], c['source'], c['target']): c['done'] for c in layout.connections}

    # One branch finished, the other running: the line into the next stage is grey
    done = lines('finished', 'in process')
    assert done[('out', '2.1', '3')] is True
    assert done[('out', '2.2', '3')] is False
    assert done[('in', None, '3')] is False
    assert done[('in', None, '2.1')] is True and done[('in', None, '2.2')] is True

    assert lines('finished', 'finished')[('in', None, '3')] is True



#-----------------------------------------------------------------------------------------------
# Steps of a stage, rendered from prepared data
#-----------------------------------------------------------------------------------------------

@pytest.fixture(scope='module')
def jinja():
    env = Environment(loader=FileSystemLoader(os.path.join(WEB_DIR, 'templates')), autoescape=select_autoescape(['html']))
    env.filters.update(template_filters.FILTERS)
    env.globals['status_view'] = status_view.get_status_view
    return env


def step_data(sequence: int, name: str, status: str, **kw) -> dict:
    return {'kind': 'step', 'top': True, 'id': sequence, 'sequence': str(sequence), 'name': name, 'environment': 'PASE', 'remote': False,
            'cmd': f"echo {name}", 'cmd_parts': [f"echo {name}"], 'status': status, 'view': status_view.get_status_view(status), 'check_error': True,
            'can_change_check': {'allowed': True, 'reason': None}, 'runs': [], 'open': status == 'failed', 'sub_steps': [], 'sub_collapsed': False,
            'parallel': kw.get('parallel', False), 'parallel_group': kw.get('group'), 'search': name}



def test_steps_of_a_parallel_group(jinja):

    # deployment_view.group_steps needs the modules of the app: the same rule here
    steps = [step_data(1, 'prep', 'finished'), step_data(2, 'g1', 'in process', parallel=True, group='build'),
             step_data(3, 'g2', 'in process', parallel=True, group='build'), step_data(4, 'pkg', 'new')]
    items = [steps[0], {'kind': 'group', 'name': 'build', 'items': steps[1:3], 'status': 'running', 'running': 2}, steps[3]]
    view = {'meta_file_id': 1, 'stage': {'id': 5, 'name': 'BUILD', 'description': '', 'status': 'in process', 'view': status_view.get_status_view('in process'), 'waiting_for': []},
            'details': [('Host', 'localhost')], 'history': [], 'buttons': [], 'items': items, 'total': 4, 'finished': 1, 'problem': False, 'latest_error': None}

    page = jinja.from_string("{% from 'overview/deployment/macros.html' import steps_panel %}{{ steps_panel(v) }}").render(v=view)

    assert 'Group <strong>build</strong>: 2 steps run at the same time, the next step waits for all of them (2 running)' in page
    group = page[page.index('<div class="ir-step-group"'):page.index('data-step-id="4"')]
    assert group.count('<div class="ir-step k-running"') == 2
    assert group.count('ir-spin') == 2
    # The step after the group is not in it, and new
    assert re.search(r'<div class="ir-step k-neutral" data-step-id="4" data-status="new"', page)
    assert page.index('data-step-id="1"') < page.index('<div class="ir-step-group"')
    assert '1 of 4 steps finished' in page



#-----------------------------------------------------------------------------------------------
# The page on the web app
#-----------------------------------------------------------------------------------------------

def step(name, cmd, **kw):
    return {'processing_step': name, 'environment': 'PASE', 'execute': cmd, 'check_error': True, **kw}


SUB_SCRIPT = '''
from modules import deploy_action as da
from modules import ibm_i_commands


def make_subs(meta_file, stage_obj, action):
    cmd = ibm_i_commands.IBM_i_commands(meta_file)
    for i in range(12):
        sub = action.sub_actions.add_action(da.Deploy_Action(cmd=f"echo sub {i}", environment=da.Command_Type.PASE,
                                                             processing_step=action.processing_step, stage=stage_obj.name, check_error=True))
        cmd.execute_action(stage=stage_obj, action=sub)
'''

PAGE_WORKFLOWS = {
    **WORKFLOWS,
    'fail_wf': {
        'name': 'fail_wf', 'default_project': 'fail', 'editable_fields': ['$.ticket'],
        'step_action': [step('quiet', 'true'), step('quick', 'echo quick'), step('broken', 'echo restoring; ls /does/not/exist'), step('after', 'echo after')],
        'stages': [
            {'name': 'START', 'next_stages': ['DEPLOY'], 'host': 'localhost', 'processing_steps': ['quick']},
            {'name': 'DEPLOY', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': ['quiet', 'quick', 'broken', 'after']},
            {'name': 'END'},
        ],
    },
    'sub_wf': {
        'name': 'sub_wf', 'default_project': 'sub',
        'step_action': [{'processing_step': 'subs', 'environment': 'SCRIPT', 'execute': 'page_subs.make_subs', 'check_error': True}],
        'stages': [
            {'name': 'START', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': ['subs']},
            {'name': 'END'},
        ],
    },
    'wait_wf': {
        'name': 'wait_wf', 'default_project': 'wait',
        'step_action': [step('slow', 'sleep 3; echo slow')],
        'stages': [
            {'name': 'START', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': ['slow']},
            {'name': 'END'},
        ],
    },
}

PAGE_USERS = {
    **USERS,
    # run only for the stage PROD of seq_wf
    'prodrunner': {'permissions': {'general': ['read'], 'workflows': {'seq_wf': {'general': [], 'stages': {'PROD': ['run']}}}}},
}

CUSTOM_TEMPLATE = '<span id="custom-marker">{{ deployment_dict["general"]["project"] }}</span>'



@pytest.fixture(scope='module')
def server():
    s = Web_Server(workflows=PAGE_WORKFLOWS, users=PAGE_USERS)
    with open(os.path.join(s.directory, 'scripts', 'page_subs.py'), 'w') as f:
        f.write(SUB_SCRIPT)
    with open(os.path.join(s.web_dir, 'templates', 'custom_templates', 'deployment_status.html'), 'w') as f:
        f.write(CUSTOM_TEMPLATE)
    s.start()
    yield s
    s.close()


@pytest.fixture()
def boss(server):
    return server.client('boss')


def page_of(client, deployment: int) -> str:
    status, _, text = client.get(f"/show_details/{deployment}", headers=HTML)
    assert status == 200, text[:300]
    return text


def text_of(markup: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', markup))).strip()


def attention(page: str) -> tuple|None:
    """(kind, text, actions of its buttons)"""
    found = re.search(r'<section class="ir-attention k-(\w+)".*?<p class="ir-attention-text">(.*?)</p>(.*?)</section>', page, re.S)
    if not found:
        return None
    return found.group(1), text_of(found.group(2)), re.findall(r'data-action="([^"]+)"', found.group(3))


def buttons(page: str, name: str) -> list[str]:
    """The <button> tags of an action"""
    return re.findall(rf'<button [^>]*data-action="{name}"[^>]*>', page)


def run(client, deployment: int, stage_name: str) -> dict:
    assert client.run_stage(deployment, stage_name)[0] == 200
    return client.wait_for_stage(deployment, stage_name, timeout=30)


def fresh(boss, workflow: str) -> int:
    from test_web_deployment import cancel_open_deployments
    cancel_open_deployments(boss, PAGE_WORKFLOWS[workflow]['default_project'])
    return boss.create_deployment(workflow, {'ticket': 'T-1'} if workflow in ('fail_wf', 'seq_wf') else None)



def test_attention_bar_for_a_ready_stage(boss):

    deployment = fresh(boss, 'seq_wf')
    try:
        kind, text, actions = attention(page_of(boss, deployment))
        assert (kind, text, actions) == ('ready', 'Stage START is ready to run.', ['run-stage'])
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_attention_bar_for_a_failed_stage(boss):

    deployment = fresh(boss, 'fail_wf')
    try:
        run(boss, deployment, 'START')
        assert run(boss, deployment, 'DEPLOY')['status'] == 'failed'

        page = page_of(boss, deployment)
        kind, text, actions = attention(page)
        assert (kind, text, actions) == ('danger', 'Stage DEPLOY failed in step broken.', ['show-log', 'run-stage', 'run-stage'])
        assert 'data-option="continue"' in page and 'data-option="run_all"' in page
        # The log of the failed run: its errors
        assert re.search(r'data-action="show-log" data-run-id="\d+" data-log-type="errors"', page)

        # The steps of the failed stage are open, at the failed step
        panel = re.search(r'<section class="ir-steps ir-card" id="stage-steps"[^>]*>', page).group(0)
        deploy_id = boss.get_stages(deployment)['DEPLOY']['id']
        failed_step = [a for a in boss.get_stages(deployment)['DEPLOY']['actions'] if a['status'] == 'failed'][0]
        assert f'data-stage-id="{deploy_id}"' in panel
        assert 'data-problem="true"' in panel and f'data-latest-error="{failed_step["id"]}"' in panel
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_attention_bar_for_a_running_stage(boss):

    deployment = fresh(boss, 'wait_wf')
    try:
        assert boss.run_stage(deployment, 'START')[0] == 200
        end = time.time() + 5
        while time.time() < end and boss.get_stages(deployment)['START']['status'] != 'in process':
            time.sleep(0.1)

        kind, text, actions = attention(page_of(boss, deployment))
        assert kind == 'running'
        assert text in ('Stage START is running: 0 of 1 steps finished.', 'Stage START is running: step 1 of 1.')
        boss.wait_for_stage(deployment, 'START', timeout=30)
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_attention_bar_for_a_stage_which_waits_for_the_service(server, boss):

    deployment = fresh(boss, 'seq_wf')
    try:
        assert boss.post_json('/api/set_processing_mode/service')[0] == 200
        status, result = boss.run_stage(deployment, 'START')
        assert status == 200 and result['service_running'] is False

        kind, text, actions = attention(page_of(boss, deployment))
        assert (kind, text, actions) == ('queued', 'Stage START waits for the processing service. The processing service is not running.', ['remove-from-queue'])
    finally:
        # First the deployment, which removes its job from the queue: then the mode can be changed
        boss.post(f"/api/cancel_deployment/{deployment}")
        assert boss.post_json('/api/set_processing_mode/thread')[0] == 200



def test_no_attention_bar_for_finished_and_canceled_deployments(boss):

    deployment = fresh(boss, 'seq_wf')
    boss.finish_deployment(deployment)
    assert boss.get_deployment(deployment)['general']['status'] == 'finished'
    page = page_of(boss, deployment)
    assert attention(page) is None
    # The last finished stage with steps is selected, its steps are closed
    assert re.search(rf'<section class="ir-steps ir-card" id="stage-steps"[^>]*data-stage-id="{boss.get_stages(deployment)["PROD"]["id"]}"[^>]*data-problem="false"', page)
    assert buttons(page, 'cancel-deployment') == []

    canceled = fresh(boss, 'seq_wf')
    boss.post(f"/api/cancel_deployment/{canceled}")
    assert attention(page_of(boss, canceled)) is None



#-----------------------------------------------------------------------------------------------
# Permissions: disabled with the reason
#-----------------------------------------------------------------------------------------------

def is_disabled(tag: str) -> bool:
    return 'aria-disabled="true"' in tag


def test_buttons_of_users_without_permission(server, boss):

    deployment = fresh(boss, 'seq_wf')
    start_id = boss.get_stages(deployment)['START']['id']

    try:
        expected = {
            # user: run START, cancel, edit custom data
            'boss': (True, True, True),
            'intern': (False, False, False),
            'runner': (True, False, False),
            'stranger': (False, False, False),
            'prodrunner': (False, False, False),
        }
        for user, allowed in expected.items():
            page = page_of(server.client(user), deployment)
            tags = [buttons(page, 'run-stage')[0], buttons(page, 'cancel-deployment')[0], buttons(page, 'edit-custom-data')[0]]
            assert [not is_disabled(tag) for tag in tags] == list(allowed), user
            for tag, ok in zip(tags, allowed, strict=True):
                if not ok:
                    assert re.search(r"title=\"Needs the permission '[^']+'", html.unescape(tag)), (user, tag)

        page = page_of(server.client('intern'), deployment)
        assert "title=\"Needs the permission 'run' for stage START\"" in html.unescape(buttons(page, 'run-stage')[0])
        assert "(Needs the permission &#39;run&#39; for stage START)" in page

        # The switch of the error check
        part = server.client('intern').get(f"/show_details/{deployment}/stage/{start_id}", headers=HTML)[2]
        assert re.search(r'data-action="check-error"[^>]* disabled title="Needs the permission &#39;change check error&#39; for stage START"', part)
        part = boss.get(f"/show_details/{deployment}/stage/{start_id}", headers=HTML)[2]
        assert not re.search(r'data-action="check-error"[^>]* disabled', part)

        # The permission for one stage: only there
        run(boss, deployment, 'START')
        page = page_of(server.client('prodrunner'), deployment)
        run_prod = [tag for tag in buttons(page, 'run-stage') if f'data-stage-id="{boss.get_stages(deployment)["PROD"]["id"]}"' in tag]
        assert run_prod and not any(is_disabled(tag) for tag in run_prod)
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



#-----------------------------------------------------------------------------------------------
# Steps of a stage
#-----------------------------------------------------------------------------------------------

def test_steps_with_sub_steps(boss):

    deployment = fresh(boss, 'sub_wf')
    try:
        run(boss, deployment, 'START')
        stage_id = boss.get_stages(deployment)['START']['id']
        status, _, part = boss.get(f"/show_details/{deployment}/stage/{stage_id}", headers=HTML)

        assert status == 200
        # 12 sub-steps, collapsed (more than 10, none failed)
        assert '<summary>12 sub-steps</summary>' in part
        assert len(re.findall(r'<span class="ir-step-seq">1\.\d+</span>', part)) == 12
        assert '<span class="ir-step-seq">1.12</span>' in part
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_steps_with_earlier_runs_and_logs(boss):

    deployment = fresh(boss, 'fail_wf')
    try:
        run(boss, deployment, 'START')
        run(boss, deployment, 'DEPLOY')
        run(boss, deployment, 'DEPLOY')
        stage_id = boss.get_stages(deployment)['DEPLOY']['id']
        part = boss.get(f"/show_details/{deployment}/stage/{stage_id}", headers=HTML)[2]

        steps = {m.group(1): m.group(0) for m in re.finditer(r'<div class="ir-step [^"]*" data-step-id="\d+" data-status="[^"]*" data-search="(\w+) .*?(?=<div class="ir-step |\Z)', part, re.S)}

        # Earlier runs of the failed step
        assert '<h4>Earlier runs</h4>' in steps['broken']
        assert len(re.findall(r'<li>', steps['broken'])) == 1
        # Log only where there is output: `true` writes nothing
        assert 'data-action="show-log"' not in steps['quiet']
        assert 'data-log-type="output"' in steps['quick'] and 'data-log-type="errors"' not in steps['quick']
        assert 'data-log-type="errors"' in steps['broken']
        # The commands as text, one part per line
        assert 'echo restoring\nls /does/not/exist</code>' in steps['broken']
        # No None and no microseconds
        assert 'None' not in text_of(part)
        assert not re.search(r'\d\d:\d\d:\d\d\.\d', part)
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_steps_need_read(server, boss):

    deployment = fresh(boss, 'fail_wf')
    try:
        stage_id = boss.get_stages(deployment)['START']['id']
        status, _, text = server.client('stranger').get(f"/show_details/{deployment}/stage/{stage_id}", headers={**HTML, 'X-Requested-With': 'fetch'})
        assert status == 403
        assert json.loads(text)['status'] == 'error'

        assert boss.get(f"/show_details/{deployment}/stage/999999", headers=HTML)[0] == 404
        # The old URL answers the same part of the page
        assert server.client('stranger').get(f"/api/get_stage_steps_html/{deployment}/{stage_id}")[0] == 403
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



#-----------------------------------------------------------------------------------------------
# Objects, empty values, custom template
#-----------------------------------------------------------------------------------------------

def test_deployment_objects(server, boss):

    from test_web_pages import add_objects, OBJECTS

    deployment = fresh(boss, 'fail_wf')
    try:
        add_objects(server, deployment)
        status, data = boss.request('GET', f"/api/deployment_objects/{deployment}")[0::2]
        data = json.loads(data)

        assert status == 200
        assert len(data['objects']) == len(OBJECTS)
        assert data['meta_file_id'] == deployment
        row = data['objects'][0]
        assert set(row) >= {'id', 'ready', 'level', 'prod_lib', 'lib', 'name', 'type', 'attribute', 'source_only', 'status', 'status_view', 'can_change'}
        assert set(row['status_view']) >= {'kind', 'icon', 'text'}

        assert server.client('stranger').get(f"/api/deployment_objects/{deployment}")[0] == 403
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_page_without_none_and_microseconds(boss):

    deployment = fresh(boss, 'fail_wf')
    try:
        page = page_of(boss, deployment)
        visible = text_of(re.sub(r'<script.*?</script>', '', page, flags=re.S))

        assert 'None' not in visible
        assert not re.search(r'\d\d:\d\d:\d\d\.\d', visible)
        assert 'Projekt' not in visible
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_custom_template_in_the_header(boss):

    deployment = fresh(boss, 'fail_wf')
    try:
        page = page_of(boss, deployment)
        actions = re.search(r'<div class="ir-page-actions">(.*?)</div>\s*</div>\s*</header>', page, re.S).group(1)
        assert '<span id="custom-marker">fail</span>' in actions
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")
