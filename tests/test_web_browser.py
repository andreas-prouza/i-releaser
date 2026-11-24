"""The web pages in a real browser (docs/features/web-ui-browser-tests.md).

Skipped if Playwright or its Chromium is not installed, see tests/browser_tools.py.
"""
import json, os, sqlite3

import pytest

from browser_tools import open_page, horizontal_overflow, wait_until
from web_server import USERS, WORKFLOWS, Web_Server


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
        paths += ['/settings', '/settings/processing', '/settings/permissions', f"/log/{log}", '/docs']

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

    assert page.locator('.ir-flow-node .ir-flow-name').all_inner_texts() == ['START', 'A->B', "It's <b>x</b>", 'QA?', 'END']

    # The dialog to run the stage after START, whose name contains '>'
    page.locator('.ir-attention [data-action="run-stage"]').click()
    page.wait_for_selector('.swal2-popup')
    assert page.locator('.swal2-title').inner_text() == 'Run A->B?'
    page.locator('.swal2-cancel').click()

    # The steps of a stage with markup in its name
    page.locator('.ir-flow-node', has_text="It's <b>x</b>").click()
    wait_until(page, "document.querySelector('#stage-steps h2').textContent === \"It's <b>x</b>\"")
    assert '#stage=' in page.url

    watch.assert_clean()



def test_values_dont_run_as_script(server, browser_context, names_deployment):

    page, watch = open_page(browser_context, server, f"/show_details/{names_deployment}")

    # Steps of START: the command contains the attack
    page.locator('.ir-flow-node', has_text='START').click()
    wait_until(page, "document.querySelector('#stage-steps h2').textContent === 'START'")
    nasty = page.locator('.ir-step', has_text='nasty')
    nasty.locator('[data-action="toggle-step"]').click()
    assert ATTACK in page.locator('#stage-steps').inner_text()
    assert page.locator('#stage-steps img[src="x"]').count() == 0

    # Its log: the output of the command
    nasty.locator('[data-action="show-log"]').first.click()
    page.wait_for_selector('#log-dialog.show')
    assert ATTACK in page.locator('#log-text').inner_text()
    page.locator('#log-dialog .btn-close').click()
    page.wait_for_selector('#log-dialog', state='hidden')

    # Switch of the object with the attack as name: an entry in the processing history
    row = page.locator('#object_list tbody tr', has_text='onerror')
    row.locator('.obj-ready').click()
    page.wait_for_timeout(500)
    page.reload(wait_until='networkidle')
    assert ATTACK in page.locator('#activity-actions').inner_text()

    assert page.evaluate("typeof window.xss") == 'undefined'

    # History of the object in the object list
    page2, watch2 = open_page(browser_context, server, '/list-objects')
    page2.locator('button[data-name*="onerror"]').first.click()
    page2.wait_for_selector('#object-history.show')
    assert ATTACK in page2.locator('#object-history-title').inner_text()
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
    wait_until(page, "$('#object_list').bootstrapTable('getData').length === 12")

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



@pytest.mark.parametrize('width', [1440, 1024, 768])
@pytest.mark.parametrize('collapsed', [False, True])
def test_no_horizontal_scrolling(server, browser_context, names_deployment, width, collapsed):

    # Settings: its tables are wider until docs/features/web-ui-admin-pages.md
    log = os.listdir(os.path.join(server.web_dir, 'log'))[0]
    if collapsed:
        browser_context.add_init_script("localStorage.setItem('ir-nav', 'collapsed')")

    for path in [f"/show_details/{names_deployment}", '/', '/list-objects', '/workflows', '/user', f"/log/{log}", '/show_details/999999']:
        page, watch = open_page(browser_context, server, path)
        page.set_viewport_size({'width': width, 'height': 900})
        page.wait_for_timeout(300)
        assert horizontal_overflow(page) <= 0, f"{path} at {width} px"
        page.close()



#-----------------------------------------------------------------------------------------------
# docs/features/web-ui-layout.md
#-----------------------------------------------------------------------------------------------

def is_collapsed(page) -> bool:
    return page.evaluate("document.documentElement.classList.contains('ir-nav-collapsed')")


def theme(page) -> str:
    return page.evaluate("document.documentElement.dataset.bsTheme")


def nav_width(page) -> float:
    return page.locator('#app-nav').bounding_box()['width']



def test_theme_and_collapsed_navigation_survive_a_reload(server, browser_context):

    page, watch = open_page(browser_context, server, '/workflows')
    assert theme(page) == 'light'
    assert not is_collapsed(page)
    assert nav_width(page) > 200

    page.locator('[data-theme-toggle]').click()
    page.locator('[data-nav-toggle]').click()
    assert theme(page) == 'dark'
    assert is_collapsed(page)
    assert page.locator('[data-theme-toggle]').get_attribute('aria-label') == 'Switch to light mode'
    assert page.locator('[data-nav-toggle]').get_attribute('aria-label') == 'Expand navigation'

    page.reload(wait_until='networkidle')
    assert theme(page) == 'dark'
    assert is_collapsed(page)
    assert nav_width(page) < 80
    # Collapsed: only icons, the text as tooltip
    assert not page.locator('[data-nav="objects"] .app-nav-text').is_visible()
    assert page.locator('[data-nav="objects"]').get_attribute('title') == 'Objects'

    # The icons stay links
    page.locator('[data-nav="objects"]').click()
    page.wait_for_url('**/list-objects')
    assert theme(page) == 'dark' and is_collapsed(page)
    assert page.locator('[data-nav="objects"]').get_attribute('aria-current') == 'page'

    page.locator('[data-nav-toggle]').click()
    page.locator('[data-theme-toggle]').click()
    page.reload(wait_until='networkidle')
    assert theme(page) == 'light' and not is_collapsed(page)

    watch.assert_clean()



def test_theme_follows_the_browser(server, browser):

    context = browser.new_context(color_scheme='dark')
    try:
        page, watch = open_page(context, server, '/')
        assert theme(page) == 'dark'

        # A choice of the user wins over the browser
        page.locator('[data-theme-toggle]').click()
        page.reload(wait_until='networkidle')
        assert theme(page) == 'light'
        watch.assert_clean()
    finally:
        context.close()



def test_logs_menu(server, browser_context):

    log = sorted(os.listdir(os.path.join(server.web_dir, 'log')))[0]
    page, watch = open_page(browser_context, server, '/')
    page.locator('[data-nav-toggle]').click()

    page.locator('[data-nav="logs"]').click()
    page.locator('#app-nav .dropdown-menu a', has_text=log).click()
    page.wait_for_url(f"**/log/{log}")
    assert page.locator('[data-nav="logs"]').get_attribute('class').split().count('active') == 1

    watch.assert_clean()



def test_navigation_on_small_screens(server, browser_context):

    page, watch = open_page(browser_context, server, '/')
    page.set_viewport_size({'width': 768, 'height': 900})
    page.wait_for_timeout(300)

    assert not page.locator('#app-nav [data-nav="workflows"]').is_visible()
    page.locator('.app-topbar [data-bs-toggle="offcanvas"]').click()
    page.locator('#app-nav [data-nav="workflows"]').click()
    page.wait_for_url('**/workflows')

    watch.assert_clean()



#-----------------------------------------------------------------------------------------------
# docs/bugfixes/minor-web-defects.md
#-----------------------------------------------------------------------------------------------

def test_log_of_the_deployment_history_closes_without_error(server, browser_context, names_deployment):

    page, watch = open_page(browser_context, server, f"/show_details/{names_deployment}")

    page.locator('#activity-runs-tab').click()
    page.locator('#activity-runs [data-action="show-log"]').first.click()
    page.wait_for_selector('#log-dialog.show')
    assert page.locator('#log-text').inner_text() != ''
    page.locator('#log-dialog .btn-close').click()
    page.wait_for_selector('#log-dialog', state='hidden')

    watch.assert_clean()



def test_token_dialogs(server, browser_context):

    page, watch = open_page(browser_context, server, '/user')

    page.locator('[data-action="new-token"]').click()
    page.locator('.swal2-confirm').click()
    wait_until(page, "Swal.getTitle() && Swal.getTitle().textContent === 'Token OBI extension created'")
    text = page.locator('.swal2-html-container').inner_text()
    assert 'shown only once' in text
    token = page.locator('.swal2-html-container code').inner_text()
    assert len(token) > 20
    assert not any(token in message for message in watch.console)

    with page.expect_navigation():
        page.locator('.swal2-confirm').click()
    page.wait_for_load_state('networkidle')

    # Canceled: nothing is sent, no second dialog
    page.locator('[data-action="delete-token"]').click()
    assert page.locator('.swal2-confirm').inner_text() == 'Delete token'
    page.locator('.swal2-cancel').click()
    page.wait_for_timeout(500)
    assert not page.locator('.swal2-popup').is_visible()
    assert [r for r in watch.requests if r.startswith('DELETE ')] == []

    # Confirmed: one dialog, then one toast (after the reload)
    page.locator('[data-action="delete-token"]').click()
    with page.expect_navigation():
        page.locator('.swal2-confirm').click()
    page.wait_for_selector('.swal2-toast')
    assert page.locator('.swal2-toast .swal2-title').inner_text() == 'Token deleted'
    assert page.locator('.swal2-popup:not(.swal2-toast)').count() == 0
    assert len([r for r in watch.requests if r.startswith('DELETE ') and '/api/v2/tokens/' in r]) == 1
    assert page.locator('[data-action="delete-token"]').count() == 0

    watch.assert_clean()



#-----------------------------------------------------------------------------------------------
# docs/features/web-ui-scripts.md
#-----------------------------------------------------------------------------------------------

def test_error_of_the_server_is_shown_with_its_message(server, browser_context):

    page, watch = open_page(browser_context, server, '/workflows')
    page.route('**/api/start_workflow/**', lambda route: route.fulfill(
        status=409, content_type='application/json', body=json.dumps({'status': 'error', 'message': 'Deployment of seq is still running'})))

    page.locator('[data-action="start-workflow"][data-workflow="seq_wf"]').click()
    assert page.locator('.swal2-title').inner_text() == 'Start seq_wf?'
    page.locator('.swal2-confirm').click()
    page.wait_for_selector('.swal2-validation-message', state='visible')
    assert page.locator('.swal2-validation-message').inner_text() == 'Deployment of seq is still running'

    watch.assert_clean(allow=('/api/start_workflow/',))



def test_ended_session_is_shown(server, browser_context):

    page, watch = open_page(browser_context, server, '/workflows?x=1')
    page.route('**/api/start_workflow/**', lambda route: route.fulfill(
        status=401, content_type='application/json', body=json.dumps({'status': 'error', 'message': 'You are not logged in'})))

    page.locator('[data-action="start-workflow"][data-workflow="seq_wf"]').click()
    page.locator('.swal2-confirm').click()
    wait_until(page, "Swal.getTitle() && Swal.getTitle().textContent === 'Your session has ended'")
    assert page.locator('.swal2-confirm').inner_text() == 'Log in'

    with page.expect_request('**/login?next=*') as login:
        page.locator('.swal2-confirm').click()
    assert login.value.url.endswith('/login?next=%2Fworkflows%3Fx%3D1')

    watch.assert_clean(allow=('/api/start_workflow/',))



def test_start_a_workflow(server, browser_context):

    page, watch = open_page(browser_context, server, '/workflows')

    page.locator('[data-action="start-workflow"][data-workflow="hidden_wf"]').click()
    with page.expect_navigation():
        page.locator('.swal2-confirm').click()
    page.wait_for_load_state('networkidle')

    deployment = int(page.url.rstrip('/').split('/')[-1])
    boss = server.client('boss')
    try:
        assert boss.get_deployment(deployment)['general']['workflow']['name'] == 'hidden_wf'
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")

    watch.assert_clean()



def test_number_of_lines_of_a_log(server, browser_context):

    log = sorted(os.listdir(os.path.join(server.web_dir, 'log')))[0]
    page, watch = open_page(browser_context, server, f"/log/{log}")

    with page.expect_navigation():
        page.locator('[data-action="log-lines"]').select_option('500')
    assert page.url.endswith(f"/log/{log}/500")
    assert page.locator('[data-action="log-lines"]').input_value() == '500'

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



def saved(page, action):
    """Does the change and waits until the page has saved it and loaded the new state"""
    with page.expect_response(lambda response: response.url.endswith('/api/permissions')):
        action()
    wait_until(page, "document.querySelector('.ir-save-state').textContent.startsWith('Saved')")


def toggle(page, level: str, permission: str, workflow: str = '', stage: str = ''):
    """The checkbox of a permission: by the data of the page, names as they are"""
    return page.locator(f'[data-action="perm-toggle"][data-level="{level}"][data-perm="{permission}"]').filter(
        has=None).and_(page.locator(f'[data-workflow="{workflow}"][data-stage="{stage}"]'))



def test_permissions_page_saves_names_with_special_characters(permission_server, browser_context):

    before = read_permissions(permission_server)

    page, watch = open_page(browser_context, permission_server, '/settings/permissions#user=intern')
    assert page.locator('#perm-detail h2').inner_text() == 'intern'

    saved(page, lambda: toggle(page, 'general', 'run').check())
    assert set(read_permissions(permission_server)['users']['intern']['permissions']['general']) == {'read', 'start workflow', 'run'}

    # A user, a workflow and a stage with special characters
    page.locator('.ir-perm-name', has_text='a.b').click()
    saved(page, lambda: toggle(page, 'stage', 'change check error', 'my.workflow', 'STAGE 2.1').check())

    after = read_permissions(permission_server)
    assert set(after['users']['a.b']['permissions']['workflows']['my.workflow']['stages']['STAGE 2.1']) == {'run', 'change check error'}

    # Nothing else changed (the page sends only the user it changes)
    def as_sets(user_data: dict) -> dict:
        permissions = user_data['permissions']
        return {
            'general': set(permissions['general']),
            'workflows': {wf: {'general': set(p.get('general', [])), 'stages': {s: set(a) for s, a in p.get('stages', {}).items()}}
                          for wf, p in permissions['workflows'].items()},
            'roles': set(user_data.get('roles', [])),
        }

    for user in ['dev#1', 'boss', 'stranger', 'runner']:
        assert as_sets(after['users'][user]) == as_sets(before['users'][user]), user
    assert set(after['roles']) == {'old role'}

    watch.assert_clean()



def test_permissions_page_undoes_a_refused_change(permission_server, browser_context):

    page, watch = open_page(browser_context, permission_server, '/settings/permissions#user=intern')
    page.route('**/api/save_permissions', lambda route: route.fulfill(status=500, content_type='application/json',
                                                                      body='{"status": "error", "message": "disk full"}'))
    toggle(page, 'general', 'run').check()

    wait_until(page, "Swal.getTitle() && Swal.getTitle().textContent === 'Not saved'")
    assert 'disk full' in page.locator('.swal2-html-container').inner_text()
    page.locator('.swal2-confirm').click()
    assert not toggle(page, 'general', 'run').is_checked()
    assert page.locator('.ir-save-state').inner_text() == 'Not saved'

    watch.assert_clean(allow=('/api/save_permissions',))



def test_permissions_page_workflow_stage_and_description(permission_server, browser_context):

    page, watch = open_page(browser_context, permission_server, '/settings/permissions#user=stranger')

    page.locator('.ir-perm-add-control select').last.select_option('par_wf')
    saved(page, lambda: page.locator('[data-action="add-workflow"]').click())
    page.locator('.ir-perm-add-control select', has=page.locator('option', has_text='Add a stage of par_wf')).select_option('A')
    saved(page, lambda: page.locator('[data-action="add-stage"][data-workflow="par_wf"]').click())
    saved(page, lambda: toggle(page, 'stage', 'run', 'par_wf', 'A').check())

    page.locator('#perm-description').fill('Externer Prüfer')
    saved(page, lambda: page.locator('#perm-mail').click())

    user = read_permissions(permission_server)['users']['stranger']
    assert user['permissions']['workflows']['par_wf'] == {'general': [], 'stages': {'A': ['run']}}
    assert user['detailed_infos']['description'] == 'Externer Prüfer'

    watch.assert_clean()



def test_permissions_page_conflict_with_another_session(permission_server, browser_context):

    page, watch = open_page(browser_context, permission_server, '/settings/permissions#user=intern')

    # Another administrator changes the permissions meanwhile
    boss = permission_server.client('boss')
    version = json.loads(boss.get('/api/permissions')[2])['version']
    assert boss.post_json('/api/save_permissions', {'version': version, 'user_permissions': {'runner': {'permissions': {'general': ['read', 'cancel workflow'], 'workflows': {}}}}})[0] == 200

    toggle(page, 'general', 'run').check()
    wait_until(page, "Swal.getTitle() && Swal.getTitle().textContent === 'Changed meanwhile'")
    page.locator('.swal2-confirm').click()

    # The current state: the change of the other session, not the click
    page.locator('.ir-perm-name', has_text='runner').click()
    assert toggle(page, 'general', 'cancel workflow').is_checked()
    assert 'run' not in read_permissions(permission_server)['users']['intern']['permissions']['general']

    watch.assert_clean(allow=('/api/save_permissions',))



def test_permissions_page_asks_before_removing_the_own_admin(permission_server, browser_context):

    page, watch = open_page(browser_context, permission_server, '/settings/permissions#user=boss')

    page.locator('#perm-admin').uncheck()
    assert page.locator('.swal2-title').inner_text() == 'Remove your own admin permission?'
    page.locator('.swal2-cancel').click()
    assert page.locator('#perm-admin').is_checked()
    assert 'admin' in read_permissions(permission_server)['users']['boss']['permissions']['general']
    assert watch.posts('/api/save_permissions') == []

    watch.assert_clean()



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



#-----------------------------------------------------------------------------------------------
# docs/features/web-ui-security-headers.md
#-----------------------------------------------------------------------------------------------

OLD_CUSTOM_TEMPLATE = """<button type="button" id="old-button" onclick="window.handler_ran = 1">Old</button>
<script>window.inline_ran = 1;</script>
"""


@pytest.fixture()
def old_template_server(browser):
    s = Web_Server()
    with open(os.path.join(s.web_dir, 'templates', 'custom_templates', 'deployment_status.html'), 'w') as f:
        f.write(OLD_CUSTOM_TEMPLATE)
    s.start()
    yield s
    s.close()



def test_inline_script_of_a_custom_template_is_blocked(old_template_server, browser_context):

    boss = old_template_server.client('boss')
    deployment = boss.create_deployment('hidden_wf')

    page, watch = open_page(browser_context, old_template_server, f"/show_details/{deployment}")
    page.locator('#old-button').click()

    assert page.evaluate("typeof window.inline_ran") == 'undefined'
    assert page.evaluate("typeof window.handler_ran") == 'undefined'
    # The browser reports both
    violations = [message for message in watch.console if 'Content Security Policy' in message]
    assert len(violations) >= 2, watch.console

    # The rest of the page works
    assert page.locator('.ir-flow-node').count() == 2
    watch.assert_clean(allow=('Content Security Policy',))
