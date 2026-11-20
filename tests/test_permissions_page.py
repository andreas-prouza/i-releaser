"""The permissions page and its Web API (docs/features/web-ui-permissions-page.md)"""
import json

import pytest

from web_server import USERS, Web_Server

# Before meta_file, which permission_config imports (circular import, see routes.py)
from modules import deploy_version  # noqa: F401
from modules import permissions, permission_config


ROLES = {'releaser': {'permissions': {'general': ['read'], 'workflows': {}}}}


@pytest.fixture()
def server():
    s = Web_Server(users=USERS)
    with open(s.path('etc', 'user_permissions.json'), 'w') as f:
        json.dump({'users': USERS, 'roles': ROLES}, f)
    s.start()
    yield s
    s.close()


@pytest.fixture()
def boss(server):
    return server.client('boss')


def read_file(server) -> dict:
    with open(server.path('etc', 'user_permissions.json')) as f:
        return json.load(f)


def state(client) -> dict:
    status, _, text = client.get('/api/permissions')
    assert status == 200, text
    return json.loads(text)


def save(client, body: dict) -> tuple[int, dict]:
    return client.post_json('/api/save_permissions', body)



def test_version_of_the_permissions(server, boss):

    version = state(boss)['version']
    assert version

    status, data = save(boss, {'version': version, 'user_permissions': {'intern': {'permissions': {'general': ['read', 'run'], 'workflows': {}}}}})
    assert status == 200
    assert data['version'] != version and data['version'] == state(boss)['version']

    # The old version: nothing changes
    before = read_file(server)
    status, data = save(boss, {'version': version, 'user_permissions': {'intern': {'permissions': {'general': [], 'workflows': {}}}}})
    assert status == 409 and 'changed meanwhile' in data['message']
    assert read_file(server) == before

    # Without a version as before (other clients)
    assert save(boss, {'user_permissions': {'intern': {'permissions': {'general': ['read'], 'workflows': {}}}}})[0] == 200

    # add_permission too
    status, data = boss.post_json('/api/add_permission', {'type': 'role', 'name': 'auditor', 'general': [], 'version': version})
    assert status == 409



@pytest.mark.parametrize('change', ['own permission', 'role of the user', 'role permission', 'delete user', 'delete role'])
def test_no_change_without_an_administrator(server, boss, change):

    # boss is the only administrator; for some cases through the role `releaser` only
    if change != 'own permission':
        role = {'releaser': {'permissions': {'general': ['admin'], 'workflows': {}}}}
        user = {'boss': {'roles': ['releaser'], 'permissions': {'general': ['read'], 'workflows': {}}}}
        assert save(boss, {'role_permissions': role, 'user_permissions': user})[0] == 200

    body = {
        'own permission': {'user_permissions': {'boss': {'permissions': {'general': ['read'], 'workflows': {}}}}},
        'role of the user': {'user_permissions': {'boss': {'roles': [], 'permissions': {'general': ['read'], 'workflows': {}}}}},
        'role permission': {'role_permissions': {'releaser': {'permissions': {'general': ['read'], 'workflows': {}}}}},
        'delete user': {'deleted_users': ['boss']},
        'delete role': {'deleted_roles': ['releaser']},
    }[change]

    before = read_file(server)
    status, data = save(boss, {**body, 'version': state(boss)['version']})
    assert status == 409, data
    assert 'no user would have the permission admin' in data['message']
    assert read_file(server) == before



NAMES = ["anna maria", "a.b", "dev#1", "pay$", "x@y", "o'neil"]


@pytest.mark.parametrize('name', NAMES)
def test_names_with_special_characters(server, boss, name):

    assert boss.post_json('/api/add_permission', {'type': 'role', 'name': name, 'general': []})[0] == 200
    status, data = boss.post_json('/api/add_permission', {'type': 'user', 'name': name, 'general': ['read']})
    assert status == 200 and data['name'] == name.lower()

    workflows = {f"wf {name}": {'general': ['read'], 'stages': {f"STAGE {name}": ['run']}}}
    assert save(boss, {'user_permissions': {name.lower(): {'roles': [name.lower()], 'permissions': {'general': ['read'], 'workflows': workflows}}},
                       'role_permissions': {name.lower(): {'permissions': {'general': [], 'workflows': workflows}}}})[0] == 200

    current = state(boss)
    assert current['users'][name.lower()]['permissions']['workflows'] == workflows
    assert current['roles'][name.lower()]['permissions']['workflows'] == workflows
    assert current['users'][name.lower()]['roles'] == [name.lower()]



@pytest.mark.parametrize('name, status', [('', 422), ('   ', 422), ('a\nb', 422), ('x' * 65, 422), ('BOSS', 409), ('releaser', 409)])
def test_names_which_are_refused(server, boss, name, status):

    kind = 'role' if name == 'releaser' else 'user'
    before = read_file(server)
    assert boss.post_json('/api/add_permission', {'type': kind, 'name': name, 'general': []})[0] == status
    assert read_file(server) == before



def test_permissions_of_a_role_for_a_workflow_and_a_stage(server, boss):

    role = {'releaser': {'permissions': {'general': [], 'workflows': {'seq_wf': {'general': ['read'], 'stages': {'START': ['run']}}}}}}
    user = {'intern': {'roles': ['releaser'], 'permissions': {'general': ['start workflow'], 'workflows': {}}}}
    assert save(boss, {'role_permissions': role, 'user_permissions': user})[0] == 200

    assert read_file(server)['roles']['releaser']['permissions']['workflows'] == role['releaser']['permissions']['workflows']

    # They count for the user: intern may run START of seq_wf now, not PROD
    intern = server.client('intern')
    deployment = intern.create_deployment('seq_wf')
    try:
        assert intern.run_stage(deployment, 'START')[0] == 200
        intern.wait_for_stage(deployment, 'START')
        assert intern.run_stage(deployment, 'PROD')[0] == 403
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")

    # Unknown roles are refused
    assert save(boss, {'user_permissions': {'intern': {'roles': ['nope'], 'permissions': {'general': [], 'workflows': {}}}}})[0] == 422



def test_description_and_mail(server, boss):

    user = {'intern': {'roles': [], 'permissions': {'general': ['read', 'start workflow'], 'workflows': {}},
                       'detailed_infos': {'description': 'Prüfer', 'mail': 'intern@example.com'}}}
    assert save(boss, {'user_permissions': user})[0] == 200
    assert state(boss)['users']['intern']['detailed_infos'] == {'description': 'Prüfer', 'mail': 'intern@example.com'}

    # Without detailed_infos they stay
    assert save(boss, {'user_permissions': {'intern': {'permissions': {'general': ['read'], 'workflows': {}}}}})[0] == 200
    assert state(boss)['users']['intern']['detailed_infos']['mail'] == 'intern@example.com'



@pytest.mark.parametrize('user', ['intern', 'runner', 'stranger'])
def test_only_for_administrators(server, user):

    client = server.client(user)
    assert client.get('/settings/permissions', headers={'Accept': 'text/html'})[0] == 403
    assert client.get('/api/permissions')[0] == 403
    assert client.post_json('/api/save_permissions', {'user_permissions': {}})[0] == 403
    assert client.post_json('/api/add_permission', {'type': 'user', 'name': 'x', 'general': []})[0] == 403



def test_page_and_its_state(server, boss):

    status, _, page = boss.get('/settings/permissions', headers={'Accept': 'text/html'})
    assert status == 200
    assert 'id="permissions-state"' in page and 'pages/permissions.js' in page

    current = state(boss)
    assert current['levels']['stage'] == ['run', 'change check error']
    assert 'admin' in current['levels']['general'] and 'admin' not in current['levels']['workflow']
    assert current['not_checked'] == ['deploy', '4-eyes check']
    assert {'name': 'seq_wf', 'stages': ['START', 'PROD', 'END']} in current['workflows']
    assert current['roles']['releaser']['users'] == []



#-----------------------------------------------------------------------------------------------
# Effective permissions: what the page shows grey
#-----------------------------------------------------------------------------------------------

A = permissions.PermissionAction


def test_effective_permissions_of_a_user_with_a_role():

    own = permissions.Permissions(general=[A.READ], workflows={'seq_wf': {'general': [A.RUN_WORKFLOW], 'stages': {'PROD': [A.CHANGE_CHECK_ERROR]}}})
    role = permissions.Permissions(general=[A.START_WORKFLOW], workflows={'SEQ_WF': {'general': [A.CANCEL_WORKFLOW], 'stages': {'start': [A.RUN_WORKFLOW]}},
                                                                         'par_wf': {'general': [A.READ], 'stages': {}}})

    effective = permission_config.get_effective(own, [('releaser', role)])

    assert effective['general'] == {'start workflow': ['role releaser']}

    seq = effective['workflows']['seq_wf']
    assert seq['general'] == {'read': ['General'], 'start workflow': ['role releaser'], 'cancel workflow': ['role releaser']}
    # Stages of the user and of the role, without case
    assert seq['stages']['PROD'] == {'read': ['General'], 'run': ['workflow seq_wf'], 'start workflow': ['role releaser'], 'cancel workflow': ['role releaser']}
    assert seq['stages']['start']['run'] == ['workflow seq_wf', 'role releaser']

    # A workflow only of the role is a row too
    assert effective['workflows']['par_wf']['general'] == {'read': ['General', 'role releaser'], 'start workflow': ['role releaser']}
