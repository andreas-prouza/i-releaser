"""The web pages in a real browser (docs/features/web-ui-browser-tests.md).

Skipped if Playwright or its Chromium is not installed, see tests/browser_tools.py.
"""
import json, os, sqlite3

import pytest

from browser_tools import browser, browser_context, open_page, horizontal_overflow
from web_server import ALL, USERS, WORKFLOWS, Web_Server


pytestmark = pytest.mark.browser


ATTACK = '<img src=x onerror="window.xss=1">'

STEPS = [
    {'processing_step': 'quick', 'environment': 'PASE', 'execute': 'echo quick', 'check_error': True},
    {'processing_step': 'nasty', 'environment': 'PASE', 'execute': f"echo 'a long command with more than 30 characters'; echo '{ATTACK}'", 'check_error': True},
]

BROWSER_WORKFLOWS = {
    **WORKFLOWS,
    # Names which broke the deployment page (docs/bugfixes/stage-name-breaks-deployment-page.md)
    'names_wf': {
        'name': 'names_wf',
        'default_project': 'names',
        'step_action': STEPS,
        'stages': [
            {'name': 'START', 'next_stages': ['A->B'], 'host': 'localhost', 'processing_steps': ['quick', 'nasty']},
            {'name': 'A->B', 'next_stages': ["It's <b>x</b>"], 'host': 'localhost', 'processing_steps': ['quick']},
            {'name': "It's <b>x</b>", 'next_stages': ['QA?'], 'host': 'localhost', 'processing_steps': ['quick']},
            {'name': 'QA?', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': ['quick']},
            {'name': 'END'},
        ],
    },
}

OBJECTS = [
    # level, name, type, attribute, deploy_status
    (1, 'orders', 'file', 'pf', 'finished'),
    (1, "o'brien", 'file', 'pf', 'new'),
    (2, ATTACK, 'file', 'lf', 'new'),
    (2, 'a"b&c', 'file', 'dspf', 'new'),
] + [(3, f"pgm{i:03}", 'pgm', 'rpgle', 'finished' if i == 0 else 'new') for i in range(12)]



@pytest.fixture(scope='module')
def server(browser):
    """Started after `browser`: without Playwright the module is skipped before the web app is started"""
    s = Web_Server(workflows=BROWSER_WORKFLOWS).start()
    yield s
    s.close()



def add_objects(server, deployment: int) -> None:

    db = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'), timeout=10)
    for level, name, type, attribute, status in OBJECTS:
        db.execute("""INSERT INTO deploy_objects (meta_file_id, level, prod_lib, lib, name, type, attribute, deploy_status, ready, properties)
                      VALUES (?, ?, 'prodlib', 'devlib', ?, ?, ?, ?, 1, '{}')""", (deployment, level, name, type, attribute, status))
    db.commit()
    db.close()



@pytest.fixture(scope='module')
def names_deployment(server):
    """Deployment with special characters in stage names, a command, custom data and objects. Stage START has run."""

    boss = server.client('boss')
    deployment = boss.create_deployment('names_wf', {'ticket': ATTACK})
    add_objects(server, deployment)

    assert boss.run_stage(deployment, 'START')[0] == 200
    boss.wait_for_stage(deployment, 'START')

    return deployment



def ready_of(server, deployment: int) -> dict:
    return {o['name']: bool(o['ready']) for o in server.client('boss').get_deployment(deployment)['objects']}



#-----------------------------------------------------------------------------------------------
# Smoke: every page without errors
#-----------------------------------------------------------------------------------------------

@pytest.mark.parametrize('user', ['boss', 'intern'])
def test_pages_have_no_errors(server, browser_context, names_deployment, user):

    log = os.listdir(os.path.join(server.web_dir, 'log'))[0]
    paths = ['/', '/project/names', '/list-objects', '/workflows', '/user', f"/show_details/{names_deployment}"]
    if user == 'boss':
        paths += ['/settings', f"/log/{log}", '/docs']

    for path in paths:
        page, watch = open_page(browser_context, server, path, user=user)
        assert page.title() is not None
        watch.assert_clean()
        page.close()

    # The error page itself has status 404, nothing else may fail
    page, watch = open_page(browser_context, server, '/show_details/999999', user=user)
    assert 'not found' in page.content()
    watch.assert_clean(allow=('/show_details/999999',))



#-----------------------------------------------------------------------------------------------
# docs/bugfixes/stage-name-breaks-deployment-page.md, web-values-run-as-script.md
#-----------------------------------------------------------------------------------------------

def test_stage_names_dont_break_the_deployment_page(server, browser_context, names_deployment):

    page, watch = open_page(browser_context, server, f"/show_details/{names_deployment}")

    assert page.evaluate("typeof run_stage") == 'function'
    assert page.locator('button[id^=flow_stage_]').all_inner_texts() == ['START', 'A->B', "It's <b>x</b>", 'QA?', 'END']

    # The dialog to run the stage after START, whose name contains '>'
    page.locator('img[title="Run Stage"]').first.click()
    page.wait_for_selector('.swal2-popup')
    assert page.locator('.swal2-title').inner_text() .startswith('Run stage A->B')
    page.locator('.swal2-cancel').click()

    watch.assert_clean()



def test_values_dont_run_as_script(server, browser_context, names_deployment):

    page, watch = open_page(browser_context, server, f"/show_details/{names_deployment}")

    # Steps of START: the command contains the attack
    page.locator('img[title="Open details"]').first.click()
    page.wait_for_selector('.swal2-popup table.stage_info')
    # A long command is folded
    page.locator('.swal2-html-container details').first.evaluate("details => details.open = true")
    assert ATTACK in page.locator('.swal2-html-container').inner_text()
    assert page.locator('.swal2-html-container img[src="x"]').count() == 0

    # Its log: the output of the command
    page.locator('.swal2-html-container img[onclick^="showActionLog"]').nth(1).click()
    page.wait_for_function("Swal.getTitle() && Swal.getTitle().textContent === 'Log'")
    assert ATTACK in page.locator('.swal2-html-container').inner_text()
    page.locator('.swal2-confirm').click()
    page.wait_for_selector('.swal2-popup table.stage_info')
    page.evaluate("Swal.close()")

    # Switch of the object with the attack as name: an entry in the processing history
    row = page.locator('#object_list tbody tr', has_text='onerror')
    row.locator('.obj-ready').click()
    page.wait_for_function("document.querySelectorAll('.swal2-popup').length === 0")
    page.wait_for_timeout(500)

    page.locator('a[title="Show history"]').click()
    page.wait_for_selector('.swal2-popup')
    assert ATTACK in page.locator('.swal2-html-container').inner_text()
    page.evaluate("Swal.close()")

    assert page.evaluate("typeof window.xss") == 'undefined'

    # History of the object in the object list
    page2, watch2 = open_page(browser_context, server, '/list-objects')
    page2.locator('button[data-name*="onerror"]').first.click()
    page2.wait_for_selector('.swal2-popup')
    assert ATTACK in page2.locator('.swal2-title').inner_text()
    assert page2.evaluate("typeof window.xss") == 'undefined'

    watch.assert_clean()
    watch2.assert_clean()



#-----------------------------------------------------------------------------------------------
# docs/bugfixes/deployment-objects-table.md
#-----------------------------------------------------------------------------------------------

def test_objects_table_none_ready_for_the_filtered_objects(server, browser_context, names_deployment):

    page, watch = open_page(browser_context, server, f"/show_details/{names_deployment}")

    assert page.evaluate("$('#object_list').bootstrapTable('getData').length") == len(OBJECTS)
    assert page.locator('#object_list tbody td', has_text='Level ').count() == 0

    page.select_option('.bootstrap-table-filter-control-type', 'pgm')
    page.wait_for_function("$('#object_list').bootstrapTable('getData').length === 12")

    watch.clear()
    page.locator('[data-objects-ready="false"]').click()
    page.wait_for_selector('.swal2-toast')
    assert page.locator('.swal2-toast .swal2-title').inner_text() == '11 objects excluded'
    assert len(watch.posts('/api/set_objects_ready/')) == 1

    # Page 2 of the filter shows the new state
    page.locator('.page-link[aria-label="to page 2"]').click()
    assert page.locator('#object_list tbody .obj-ready:checked').count() == 0

    ready = ready_of(server, names_deployment)
    assert ready['pgm000'] is True            # finished
    assert not any(ready[f"pgm{i:03}"] for i in range(1, 12))
    assert ready["o'brien"] is True and ready['a"b&c'] is True

    watch.assert_clean()



def test_objects_with_special_characters_can_be_switched(server, browser_context, names_deployment):

    page, watch = open_page(browser_context, server, f"/show_details/{names_deployment}")

    for name in ["o'brien", 'a"b&c']:
        before = ready_of(server, names_deployment)[name]
        page.locator('#object_list tbody tr', has_text=name).locator('.obj-ready').click()
        page.wait_for_timeout(500)
        assert ready_of(server, names_deployment)[name] is (not before)

    # Finished objects can't be switched
    assert page.locator('#object_list tbody tr', has_text='orders').locator('.obj-ready').is_disabled()

    watch.assert_clean()



@pytest.mark.parametrize('width', [1440, 1024])
def test_no_horizontal_scrolling(server, browser_context, names_deployment, width):

    browser_context.pages and None
    for path in [f"/show_details/{names_deployment}", '/', '/list-objects', '/workflows']:
        page, watch = open_page(browser_context, server, path)
        page.set_viewport_size({'width': width, 'height': 900})
        page.wait_for_timeout(300)
        assert horizontal_overflow(page) <= 0, f"{path} at {width} px"
        page.close()



#-----------------------------------------------------------------------------------------------
# docs/bugfixes/minor-web-defects.md
#-----------------------------------------------------------------------------------------------

def test_log_of_the_deployment_history_closes_without_error(server, browser_context, names_deployment):

    page, watch = open_page(browser_context, server, f"/show_details/{names_deployment}")

    page.locator('img[onclick^="showLog"]').first.click()
    page.wait_for_selector('.swal2-popup')
    page.locator('.swal2-confirm').click()
    page.wait_for_timeout(500)

    watch.assert_clean()



def test_token_dialogs(server, browser_context):

    page, watch = open_page(browser_context, server, '/user')

    page.locator('button[onclick="renew_key()"]').click()
    page.locator('.swal2-confirm').click()
    page.wait_for_function("Swal.getTitle() && Swal.getTitle().textContent === 'Token successfully generated!'")
    text = page.locator('.swal2-html-container').inner_text()
    assert 'shown only once' in text
    token = page.locator('.swal2-html-container code').inner_text()
    assert len(token) > 20
    assert not any(token in message for message in watch.console)

    page.locator('.swal2-confirm').click()
    page.wait_for_load_state('networkidle')

    page.locator('button[onclick="drop_key()"]').click()
    assert page.locator('.swal2-confirm').inner_text() == 'Delete token'
    watch.clear()
    page.locator('.swal2-confirm').click()
    page.wait_for_function("Swal.getTitle() && Swal.getTitle().textContent === 'Deleted'")
    assert len(watch.posts('/api/drop_key')) == 1

    watch.assert_clean()



#-----------------------------------------------------------------------------------------------
# docs/bugfixes/permissions-page-names-in-selectors.md
#-----------------------------------------------------------------------------------------------

PERMISSION_USERS = {
    **USERS,
    'a.b': {'roles': [], 'permissions': {'general': ['read'], 'workflows': {'my.workflow': {'general': ['run'], 'stages': {'STAGE 2.1': ['run'], 'Create object list': ['run'], "It's <b>x</b>": []}}}}},
    'dev#1': {'roles': ['old role'], 'permissions': {'general': ['read'], 'workflows': {}}},
}


@pytest.fixture()
def permission_server(browser):

    s = Web_Server(users=PERMISSION_USERS).start()
    with open(s.path('etc', 'user_permissions.json'), 'w') as f:
        json.dump({'users': PERMISSION_USERS, 'roles': {'old role': {'permissions': {'general': ['read'], 'workflows': {}}}}}, f)
    yield s
    s.close()



def read_permissions(server) -> dict:
    with open(server.path('etc', 'user_permissions.json')) as f:
        return json.load(f)



def test_permissions_page_saves_names_with_special_characters(permission_server, browser_context):

    before = read_permissions(permission_server)

    page, watch = open_page(browser_context, permission_server, '/settings')
    page.locator('.tablinks', has_text='Permission').click()

    page.locator('[data-kind="user-general"][data-user="intern"][data-value="run"]').click()
    page.wait_for_function("Swal.getTitle() && Swal.getTitle().textContent === 'Permissions has been saved'")

    after = read_permissions(permission_server)
    assert set(after['users']['intern']['permissions']['general']) == {'read', 'start workflow', 'run'}

    # The page sends the permissions in the order of its checkboxes: compare them as sets
    def as_sets(user_data: dict) -> dict:
        permissions = user_data['permissions']
        return {
            'general': set(permissions['general']),
            'workflows': {wf: {'general': set(p.get('general', [])), 'stages': {s: set(a) for s, a in p.get('stages', {}).items()}}
                          for wf, p in permissions['workflows'].items()},
            'roles': set(user_data.get('roles', [])),
        }

    for user in ['a.b', 'dev#1', 'boss', 'stranger', 'runner']:
        assert as_sets(after['users'][user]) == as_sets(before['users'][user]), user
    assert set(after['roles']) == {'old role'}

    watch.assert_clean()



def test_permissions_page_shows_save_errors(permission_server, browser_context):

    page, watch = open_page(browser_context, permission_server, '/settings')
    page.route('**/api/save_permissions', lambda route: route.fulfill(status=500, content_type='application/json',
                                                                      body='{"status": "error", "message": "disk full"}'))
    page.locator('.tablinks', has_text='Permission').click()
    page.locator('[data-kind="user-general"][data-user="intern"][data-value="run"]').click()

    page.wait_for_function("Swal.getTitle() && Swal.getTitle().textContent === 'Failed to save permission'")
    assert 'disk full' in page.locator('.swal2-html-container').inner_text()

    watch.assert_clean(allow=('/api/save_permissions', 'Error saving permission'))



#-----------------------------------------------------------------------------------------------
# Custom template with a script file (docs/examples/rollback, docs/scripts.md#web-app-extensions)
#-----------------------------------------------------------------------------------------------

EXAMPLE_DIR = os.path.join(os.path.dirname(__file__), '..', 'docs', 'examples', 'rollback')

ROLLBACK_WORKFLOW = {
    'name': 'rollback_deployment',
    'default_project': 'seq',
    'parallel_deployment_execution_allowed': True,
    'create_fields': ['$.project', '$.version'],
    'step_action': [{'processing_step': 'quick', 'environment': 'PASE', 'execute': 'echo quick', 'check_error': True}],
    'stages': [
        {'name': 'START', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': ['quick']},
        {'name': 'END'},
    ],
}


@pytest.fixture()
def rollback_server(browser):
    """The example of the docs as custom template and script of the installation"""

    import shutil

    s = Web_Server(workflows={**WORKFLOWS, 'rollback_deployment': ROLLBACK_WORKFLOW})
    shutil.copy(os.path.join(EXAMPLE_DIR, 'deployment_status.html'), os.path.join(s.web_dir, 'templates', 'custom_templates', 'deployment_status.html'))
    os.makedirs(os.path.join(s.web_dir, 'static', 'custom'), exist_ok=True)
    shutil.copy(os.path.join(EXAMPLE_DIR, 'rollback.js'), os.path.join(s.web_dir, 'static', 'custom', 'rollback.js'))
    s.start()
    yield s
    s.close()



def test_rollback_example_has_no_javascript_in_the_template():
    """The form a custom template needs with the Content-Security-Policy"""

    import re

    with open(os.path.join(EXAMPLE_DIR, 'deployment_status.html'), encoding='utf-8') as f:
        template = f.read()

    assert not re.search(r'\son\w+\s*=', template)
    assert re.findall(r'<script\b[^>]*>', template) == ['<script type="module" src="{{ url_for(\'static\', path=\'custom/rollback.js\') }}">']
    assert 'javascript:' not in template



def test_rollback_example_starts_the_rollback_workflow(rollback_server, browser_context):

    boss = rollback_server.client('boss')
    deployment = boss.create_deployment('seq_wf')
    boss.finish_deployment(deployment)
    assert boss.get_deployment(deployment)['general']['status'] == 'finished'

    page, watch = open_page(browser_context, rollback_server, f"/show_details/{deployment}")

    page.locator('[data-rollback]').click()
    page.wait_for_selector('.swal2-popup')
    assert 'for seq, version 1' in page.locator('.swal2-html-container').inner_text()

    with page.expect_navigation():
        page.locator('.swal2-confirm').click()

    rollback_id = int(page.url.rstrip('/').split('/')[-1])
    rollback = boss.get_deployment(rollback_id)
    assert rollback['general']['workflow']['name'] == 'rollback_deployment'
    assert rollback['custom_data'] == {'project': 'seq', 'version': '1'}

    # The page of the rollback links to the deployment it rolls back
    page.wait_for_load_state('networkidle')
    assert page.locator('a[href="/show_details/seq/1"]').count() == 1

    watch.assert_clean()



def test_rollback_example_shows_errors_of_the_server(rollback_server, browser_context):

    boss = rollback_server.client('boss')
    deployment = boss.create_deployment('seq_wf')
    boss.finish_deployment(deployment)

    page, watch = open_page(browser_context, rollback_server, f"/show_details/{deployment}")
    page.route('**/api/start_workflow/rollback_deployment', lambda route: route.fulfill(
        status=403, content_type='application/json', body='{"status": "error", "message": "User boss may not start rollback_deployment"}'))

    page.locator('[data-rollback]').click()
    page.locator('.swal2-confirm').click()
    page.wait_for_selector('.swal2-validation-message', state='visible')
    assert 'may not start rollback_deployment' in page.locator('.swal2-validation-message').inner_text()

    watch.assert_clean(allow=('/api/start_workflow/rollback_deployment',))



#-----------------------------------------------------------------------------------------------
# Screenshots of the documentation (tests/screenshots.py)
#-----------------------------------------------------------------------------------------------

def test_screenshots_script(browser, tmp_path):

    import screenshots

    written = screenshots.make_screenshots(str(tmp_path), browser)

    assert sorted(os.path.basename(f) for f in written) == sorted(f"{name}.png" for name in screenshots.SCREENSHOTS)
    for file in written:
        with open(file, 'rb') as f:
            assert f.read(8) == b'\x89PNG\r\n\x1a\n', file

    # Every picture of README.md is made by the script
    with open(os.path.join(os.path.dirname(__file__), '..', 'README.md'), encoding='utf-8') as f:
        readme = f.read()
    import re
    pictures = {name for name in re.findall(r'docs/img/([\w-]+)\.png', readme) if name != 'logo2-icon'}
    assert pictures == set(screenshots.SCREENSHOTS)
