"""The pages of the web app: where their files come from (docs/bugfixes/web-scripts-from-third-party-servers.md)"""
import os, re

import pytest

from web_server import ROOT_DIR, Web_Server


@pytest.fixture(scope='module')
def server():
    s = Web_Server().start()
    yield s
    s.close()


@pytest.fixture()
def boss(server):
    return server.client('boss')


# What a page loads: src of everything, href of <link>, url(...) and @import in styles
LOADED = [
    re.compile(r'<(?:script|img|iframe|audio|video|source|embed)\b[^>]*?\bsrc\s*=\s*["\']?([^"\'\s>]+)', re.I),
    re.compile(r'<link\b[^>]*?\bhref\s*=\s*["\']?([^"\'\s>]+)', re.I),
    re.compile(r'url\(\s*["\']?([^"\')\s]+)', re.I),
    re.compile(r'@import\s+["\']([^"\']+)', re.I),
]


def get_foreign_urls(text: str, own_origin: str|None=None) -> list:
    """URLs a browser would load from another server. `url_for` writes the own host into the URL."""

    urls = [url for pattern in LOADED for url in pattern.findall(text)]
    urls = [url for url in urls if url.startswith(('http:', 'https:', '//'))]

    return [url for url in urls if own_origin is None or not url.startswith(f"{own_origin}/")]



def test_get_foreign_urls():

    assert get_foreign_urls('<script src="https://cdn.example/x.js"></script>') == ['https://cdn.example/x.js']
    assert get_foreign_urls("<link rel=stylesheet href='//cdn.example/x.css'>") == ['//cdn.example/x.css']
    assert get_foreign_urls('<style>@import "http://cdn.example/x.css"; a {background: url(https://cdn.example/x.png)}</style>') != []
    assert get_foreign_urls('<a href="https://prouza.at">x</a><script src="/static/x.js"></script>') == []
    assert get_foreign_urls('<script src="http://127.0.0.1:80/static/x.js"></script>', 'http://127.0.0.1:80') == []
    assert get_foreign_urls('<script src="http://127.0.0.1:80.evil.example/x.js"></script>', 'http://127.0.0.1:80') != []



def test_pages_load_nothing_from_other_servers(server, boss):

    deployment = boss.create_deployment('hidden_wf')
    log = os.listdir(os.path.join(server.web_dir, 'log'))[0]

    try:
        for path in ['/', '/list-objects', '/workflows', '/settings', '/user', f"/log/{log}", f"/show_details/{deployment}", '/show_details/999999', '/docs']:
            status, _, text = boss.get(path, headers={'Accept': 'text/html'})
            assert status in [200, 404], path
            assert '<html' in text.lower(), path
            assert get_foreign_urls(text, boss.origin) == [], path
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")

    status, _, text = server.client().get('/', headers={'Accept': 'text/html'})
    assert 'name="password"' in text
    assert get_foreign_urls(text, boss.origin) == []



def test_templates_and_scripts_load_nothing_from_other_servers():

    web_dir = os.path.join(ROOT_DIR, 'webapp')
    own_files = [os.path.join(web_dir, 'static', 'assets', 'js', name) for name in ['web.deploy.js', 'chart.js']]
    own_files.append(os.path.join(web_dir, 'static', 'assets', 'css', 'global.css'))

    for directory, _, names in os.walk(os.path.join(web_dir, 'templates')):
        # Templates of the installation are not part of the repository
        if os.path.basename(directory) == 'custom_templates':
            continue
        own_files += [os.path.join(directory, name) for name in names if name.endswith('.html')]

    for file in own_files:
        with open(file, encoding='utf-8') as f:
            text = f.read()
        assert get_foreign_urls(text) == [], file
        assert not re.search(r'import\s*\(?\s*["\'](https?:)?//', text), file
        assert not re.search(r'setAttribute\(\s*["\']src["\']\s*,\s*["\'](https?:)?//', text), file



def test_api_docs_use_local_files(server, boss):

    status, _, text = boss.get('/docs', headers={'Accept': 'text/html'})
    assert status == 200
    assert '/static/assets/swagger-ui/swagger-ui-bundle.js' in text

    for file in ['swagger-ui-bundle.js', 'swagger-ui.css']:
        assert boss.get(f"/static/assets/swagger-ui/{file}")[0] == 200

    assert boss.get('/openapi.json')[0] == 200



def test_api_docs_need_a_login(server):

    status, _, text = server.client().get('/docs', headers={'Accept': 'text/html'})
    assert 'swagger' not in text.lower()



def test_no_redoc(server, boss):
    assert boss.get('/redoc', headers={'Accept': 'text/html'})[0] == 404



#-----------------------------------------------------------------------------------------------
# Values are data, not HTML or script (docs/bugfixes/web-values-run-as-script.md,
# docs/bugfixes/stage-name-breaks-deployment-page.md)
#-----------------------------------------------------------------------------------------------

ATTACK = '<img src=x onerror="window.xss=1">'

NASTY_STAGES = ["A->B", "QA?", "It's done", "Prüfung <1>", "STAGE 2.1", f"S {ATTACK}"]

NASTY_WORKFLOW = {
    'name': 'nasty_wf',
    'default_project': 'nasty',
    'step_action': [
        {'processing_step': 'short', 'environment': 'PASE', 'execute': "echo '<b>&\"'", 'check_error': True},
        {'processing_step': 'long', 'environment': 'PASE', 'execute': f"echo 'a long command with more than 30 characters'; echo '{ATTACK}'", 'check_error': True},
    ],
    'stages': [{'name': 'START', 'next_stages': [NASTY_STAGES[0]], 'host': 'localhost', 'processing_steps': ['short', 'long']}]
            + [{'name': name, 'next_stages': [next_name], 'host': 'localhost', 'processing_steps': ['short']} for name, next_name in zip(NASTY_STAGES, NASTY_STAGES[1:] + ['END'])]
            + [{'name': 'END'}],
}

NASTY_OBJECTS = [("o'brien", 'devlib'), (ATTACK, "lib'x"), ('a"b&c', 'devlib')]


@pytest.fixture(scope='module')
def nasty_server():
    from web_server import WORKFLOWS
    s = Web_Server(workflows={**WORKFLOWS, 'nasty_wf': NASTY_WORKFLOW}).start()
    yield s
    s.close()


@pytest.fixture(scope='module')
def nasty_deployment(nasty_server):

    import sqlite3

    boss = nasty_server.client('boss')
    deployment = boss.create_deployment('nasty_wf', {'ticket': ATTACK})

    db = sqlite3.connect(os.path.join(nasty_server.directory, 'var', 'app.sqlite'), timeout=10)
    for name, lib in NASTY_OBJECTS:
        db.execute("""INSERT INTO deploy_objects (meta_file_id, level, prod_lib, lib, name, type, attribute, deploy_status, ready, properties)
                      VALUES (?, 1, ?, ?, ?, 'file', 'pf', 'new', 1, '{}')""", (deployment, lib, lib, name))
    db.commit()
    db.close()

    return deployment


def check_no_markup_from_data(text: str, where: str) -> None:

    # The only way the attack may appear: escaped
    assert '<img src=x' not in text, where
    assert 'onerror="window.xss' not in text, where

    # No value of the test data inside JavaScript: inline handlers and scripts get their values from data-* attributes
    for handler in re.findall(r'\son\w+\s*=\s*"([^"]*)"', text):
        for value in ["brien", "lib&#39;x", "It&#39;s", "window.xss", "&lt;img"]:
            assert value not in handler, f"{where}: {handler}"



def test_deployment_page_escapes_values(nasty_server, nasty_deployment):

    boss = nasty_server.client('boss')
    status, _, text = boss.get(f"/show_details/{nasty_deployment}", headers={'Accept': 'text/html'})

    assert status == 200
    check_no_markup_from_data(text, 'deployment page')

    # The values are there, as text
    assert 'o&#39;brien' in text
    assert '&lt;img src=x onerror=' in text
    assert 'It&#39;s done' in text
    assert 'Prüfung &lt;1&gt;' in text

    # The handler of an object reads its values from the element
    assert 'data-name="o&#39;brien"' in text
    assert 'this.dataset.name' in text



def test_deployment_page_has_no_script_generated_from_stage_names(nasty_server, nasty_deployment):

    boss = nasty_server.client('boss')
    _, _, text = boss.get(f"/show_details/{nasty_deployment}", headers={'Accept': 'text/html'})

    # Stages are identified by their id. A code of the name can contain characters which are not allowed in JavaScript names.
    variables = re.findall(r'^\s*let (\S+) = document\.getElementById\("([^"]+)"\);', text, re.M)
    variables = [v for v in variables if v[1] not in ['flow_parent', 'flowchart']]
    assert len(variables) == len(NASTY_STAGES) + 2
    for variable, element_id in variables:
        assert re.fullmatch(r'flow_stage_\d+', variable), variable
        assert variable == element_id
        assert f'id="{element_id}"' in text

    for connection in re.findall(r'^\s*connectItems\((.*)\);', text, re.M):
        assert re.fullmatch(r'flow_stage_\d+, flow_stage_\d+, "\w+", "\w+"', connection), connection



def test_steps_of_a_stage_escape_values(nasty_server, nasty_deployment):

    boss = nasty_server.client('boss')
    stages = boss.get_stages(nasty_deployment)

    for name in ['START', NASTY_STAGES[-1], "It's done"]:
        status, data = boss.request('GET', f"/api/get_stage_steps_html/{nasty_deployment}/{stages[name]['id']}")[0::2]
        assert status == 200
        html = __import__('json').loads(data)['html']
        check_no_markup_from_data(html, f"steps of {name}")

    html = __import__('json').loads(boss.get(f"/api/get_stage_steps_html/{nasty_deployment}/{stages['START']['id']}")[2])['html']

    # Commands are shown as text, the parts of a long command on their own lines
    assert "echo &#39;&lt;b&gt;&amp;&#34;&#39;" in html
    assert "&lt;img src=x onerror=" in html
    assert "characters&#39;\n\necho" in html



def test_object_list_escapes_values(nasty_server, nasty_deployment):

    boss = nasty_server.client('boss')
    status, _, text = boss.get('/list-objects', headers={'Accept': 'text/html'})

    assert status == 200
    check_no_markup_from_data(text, 'object list')
    assert 'data-name="o&#39;brien"' in text
    assert 'data-prod-lib="lib&#39;x"' in text



def test_templates_have_no_values_in_inline_javascript():
    """`onclick="f('{{ value }}')"`: the browser turns `&#39;` back into `'` before it runs the handler"""

    templates = os.path.join(ROOT_DIR, 'webapp', 'templates')

    for directory, _, names in os.walk(templates):
        if os.path.basename(directory) == 'custom_templates':
            continue
        for name in names:
            with open(os.path.join(directory, name), encoding='utf-8') as f:
                text = f.read()
            for handler in re.findall(r'\son\w+\s*=\s*"([^"]*)"', text, re.I):
                assert not re.search(r"'\s*\{\{", handler), f"{name}: {handler}"
            # Data is never marked as safe. The two buttons and the flow chart are HTML of flowchart.py, which escapes its values.
            for expression in re.findall(r'\{\{([^}]*\|\s*safe\s*)\}\}', text):
                assert expression.split('|')[0].strip() in ['run_stage_button', 'reset_stage_button', 'flow_html', 'flow_javascript'], f"{name}: {expression}"



def test_scripts_escape_values_of_the_server():

    with open(os.path.join(ROOT_DIR, 'webapp', 'templates', 'overview', 'show-deployment.html'), encoding='utf-8') as f:
        deployment_page = f.read()
    with open(os.path.join(ROOT_DIR, 'webapp', 'templates', 'overview', 'list-objects.html'), encoding='utf-8') as f:
        object_list = f.read()

    # Processing history and object history are tables built by JavaScript
    assert '${item.details' not in deployment_page and '${item.user}' not in deployment_page
    assert 'escape_html(item.details)' in deployment_page
    assert '${row[key]}</' not in object_list and '>${row[key]}' not in object_list
    assert 'escape_html(row[key])' in object_list



#-----------------------------------------------------------------------------------------------
# Permissions (docs/bugfixes/permissions-page-names-in-selectors.md)
#-----------------------------------------------------------------------------------------------

def read_permissions(server) -> dict:
    with open(server.path('etc', 'user_permissions.json')) as f:
        return __import__('json').load(f)



@pytest.fixture()
def permission_server():
    from web_server import USERS
    users = {**USERS,
             'a.b': {'permissions': {'general': ['read'], 'workflows': {'my.workflow': {'general': ['run'], 'stages': {'STAGE 2.1': ['run'], 'Create object list': ['run']}}}}},
             'dev#1': {'permissions': {'general': ['read'], 'workflows': {}}}}
    s = Web_Server(users=users).start()
    with open(s.path('etc', 'user_permissions.json'), 'w') as f:
        __import__('json').dump({'users': users, 'roles': {'releaser': {'permissions': {'general': ['read'], 'workflows': {}}}, 'old role': {'permissions': {'general': [], 'workflows': {}}}}}, f)
    yield s
    s.close()



def test_save_permissions_keeps_users_and_roles_which_are_not_sent(permission_server):

    boss = permission_server.client('boss')
    before = read_permissions(permission_server)

    status, data = boss.post_json('/api/save_permissions', {
        'user_permissions': {'intern': {'roles': ['releaser'], 'permissions': {'general': ['read'], 'workflows': {}}}},
        'role_permissions': {},
    })
    assert status == 200, data

    after = read_permissions(permission_server)
    assert set(after['users']) == set(before['users'])
    assert set(after['roles']) == set(before['roles'])
    assert after['users']['intern']['roles'] == ['releaser']
    assert after['users']['intern']['permissions']['general'] == ['read']
    assert after['users']['a.b']['permissions']['workflows']['my.workflow']['stages'] == {'STAGE 2.1': ['run'], 'Create object list': ['run']}
    assert after['users']['boss'] == before['users']['boss'] or after['users']['boss']['permissions'] == before['users']['boss']['permissions']



def test_save_permissions_deletes_only_what_is_named(permission_server):

    boss = permission_server.client('boss')

    status, data = boss.post_json('/api/save_permissions', {
        'user_permissions': {}, 'role_permissions': {}, 'deleted_users': ['dev#1'], 'deleted_roles': ['old role'],
    })
    assert status == 200, data

    after = read_permissions(permission_server)
    assert 'dev#1' not in after['users']
    assert 'old role' not in after['roles']
    assert {'boss', 'intern', 'a.b'} <= set(after['users'])
    assert 'releaser' in after['roles']



def test_save_permissions_rejects_unknown_users(permission_server):

    boss = permission_server.client('boss')
    before = read_permissions(permission_server)

    status, data = boss.post_json('/api/save_permissions', {
        'user_permissions': {'nobody': {'roles': [], 'permissions': {'general': ['admin'], 'workflows': {}}}}, 'role_permissions': {},
    })

    assert status in [400, 422], data
    assert read_permissions(permission_server) == before



def test_permissions_page_keeps_names_out_of_selectors(permission_server):

    boss = permission_server.client('boss')
    status, _, text = boss.get('/settings', headers={'Accept': 'text/html'})
    assert status == 200

    # Names are data-* attributes of the checkboxes, and the page compares them as text
    assert 'data-kind="user-stage-permission" data-user="a.b"' in text
    assert 'data-stage="STAGE 2.1"' in text
    assert 'data-kind="user-general" data-user="dev#1"' in text
    assert 'class="user-' not in text and 'class="role-' not in text
    assert not re.search(r'querySelectorAll\(`[^`]*\$\{(user|role|workflow|stage)', text)
