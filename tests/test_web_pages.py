"""The pages of the web app: where their files come from (docs/bugfixes/web-scripts-from-third-party-servers.md)"""
import json, os, re

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
        for path in ['/', '/list-objects', '/workflows', '/settings', '/settings/processing', '/settings/permissions', '/settings/security', '/settings/audit', '/settings/configuration', '/user', f"/log/{log}", f"/show_details/{deployment}", '/show_details/999999', '/docs']:
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
    own_files = [os.path.join(web_dir, 'static', 'assets', 'js', 'swagger-init.js'), os.path.join(web_dir, 'static', 'assets', 'css', 'app.css')]
    for folder in ['app', 'pages']:
        directory = os.path.join(web_dir, 'static', 'assets', 'js', folder)
        own_files += [os.path.join(directory, name) for name in os.listdir(directory)]

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
            + [{'name': name, 'next_stages': [next_name], 'host': 'localhost', 'processing_steps': ['short']} for name, next_name in zip(NASTY_STAGES, NASTY_STAGES[1:] + ['END'], strict=True)]
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
    assert '&lt;img src=x onerror=' in text
    assert 'It&#39;s done' in text
    assert 'Prüfung &lt;1&gt;' in text

    # The objects are data for the script of the table, not HTML
    names = [o['name'] for o in get_objects_table(text)['objects']]
    assert sorted(names) == sorted(name for name, _ in NASTY_OBJECTS)



def test_deployment_page_has_no_script_generated_from_stage_names(nasty_server, nasty_deployment):

    boss = nasty_server.client('boss')
    _, _, text = boss.get(f"/show_details/{nasty_deployment}", headers={'Accept': 'text/html'})

    # No script code in the page: stages are identified by their id, the names are only text
    for attributes, content in re.findall(r'<script\b([^>]*)>(.*?)</script>', text, re.S):
        assert 'application/json' in attributes or not content.strip(), content[:80]

    stage_ids = re.findall(r'class="ir-flow-node[^"]*"[^>]*data-action="select-stage" data-stage-id="([^"]+)"', text)
    assert len(stage_ids) == len(NASTY_STAGES) + 2
    assert all(re.fullmatch(r'\d+', stage_id) for stage_id in stage_ids)
    assert 'Prüfung &lt;1&gt;' in text and "It&#39;s done" in text



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
    assert "characters&#39;\necho" in html

    # The same part of the page under its own URL
    status, _, part = boss.get(f"/show_details/{nasty_deployment}/stage/{stages['START']['id']}", headers={'Accept': 'text/html'})
    assert status == 200
    assert part.strip() == html.strip()



def test_object_list_escapes_values(nasty_server, nasty_deployment):

    boss = nasty_server.client('boss')
    status, _, text = boss.get('/list-objects', headers={'Accept': 'text/html'})

    assert status == 200
    check_no_markup_from_data(text, 'object list')

    # The rows come as data (escaped by the script of the page, see test_scripts_escape_values_of_the_server)
    rows = __import__('json').loads(boss.get('/api/deploy_objects?limit=100')[2])['rows']
    assert {"o'brien", ATTACK, 'a"b&c'} <= {row['name'] for row in rows}

    # The history of an object: a part of the page from the server
    from urllib.parse import urlencode
    query = urlencode({'project': 'nasty', 'prod_lib': "lib'x", 'name': ATTACK, 'type': 'file', 'attribute': 'pf'})
    status, _, history = boss.get(f"/list-objects/history?{query}", headers={'Accept': 'text/html'})
    assert status == 200
    check_no_markup_from_data(history, 'object history')
    assert 'data-title="&lt;img src=x' in history
    assert '/show_details/' in history



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
            # Data is never marked as safe
            assert not re.search(r'\|\s*safe\b', text), name



def test_scripts_escape_values_of_the_server():

    with open(os.path.join(ROOT_DIR, 'webapp', 'templates', 'overview', 'show-deployment.html'), encoding='utf-8') as f:
        deployment_page = f.read()
    with open(os.path.join(ROOT_DIR, 'webapp', 'static', 'assets', 'js', 'pages', 'objects.js'), encoding='utf-8') as f:
        object_list = f.read()

    # The processing history is a table of the template, the history of an object a part of a page from the server
    assert '<script>' not in deployment_page and '${' not in deployment_page
    assert '{{ row.details | or_dash }}' in deployment_page
    # The button of the history: values of the row only escaped
    assert '${row[key]}' not in object_list
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
    status, _, text = boss.get('/settings/permissions', headers={'Accept': 'text/html'})
    assert status == 200

    # Names are data of the page (a JSON block); the script builds the table with the DOM and compares names as text
    state = __import__('json').loads(__import__('html').unescape(re.search(r'id="permissions-state">(.*?)</script>', text, re.S).group(1)))
    assert state['users']['a.b']['permissions']['workflows']['my.workflow']['stages']['STAGE 2.1'] == ['run']
    assert 'dev#1' in state['users']
    assert 'class="user-' not in text and 'class="role-' not in text

    with open(os.path.join(ROOT_DIR, 'webapp', 'static', 'assets', 'js', 'pages', 'permissions.js'), encoding='utf-8') as f:
        script = f.read()
    assert not re.search(r'querySelector(All)?\(`[^`]*\$\{', script)
    assert 'innerHTML' not in script



#-----------------------------------------------------------------------------------------------
# Static files (docs/features/web-ui-static-assets.md)
#-----------------------------------------------------------------------------------------------

STATIC_DIR = os.path.join(ROOT_DIR, 'webapp', 'static')

# Not referred to by a page of the repository
STATIC_FILES_WITHOUT_REFERENCE = [
    # licenses of the libraries
    r'assets/licenses/.*',
    r'assets/swagger-ui/(LICENSE|NOTICE|swagger-ui-bundle\.js\.LICENSE\.txt)',
    # scripts of an installation (custom templates)
    r'custom/.*',
    # Images of the old pages: custom templates may use them (docs/features/web-ui-static-assets.md, requirement 5)
    r'assets/img/(cancel|run-green|undo|inspect|log|error-log)\.png',
]


def get_static_files() -> list:
    files = []
    for directory, _, names in os.walk(STATIC_DIR):
        files += [os.path.relpath(os.path.join(directory, name), STATIC_DIR).replace(os.sep, '/') for name in names]
    return files



def get_own_sources() -> str:
    """Templates, Python code of the web app and the own scripts and stylesheets: everything which can refer to a static file"""

    web_dir = os.path.join(ROOT_DIR, 'webapp')
    text = ''

    # Own scripts import their modules (pages/*.js -> app/*.js)
    own_scripts = [os.path.join('static', 'assets', 'js', 'app'), os.path.join('static', 'assets', 'js', 'pages')]

    for top in ['templates', 'web_modules', 'routes', os.path.join('static', 'assets', 'css'), os.path.join('static', 'assets', 'bootstrap', 'font')] + own_scripts:
        for directory, _, names in os.walk(os.path.join(web_dir, top)):
            if os.path.basename(directory) in ['custom_templates', '__pycache__']:
                continue
            for name in names:
                if name.endswith(('.html', '.py', '.css', '.js')):
                    with open(os.path.join(directory, name), encoding='utf-8') as f:
                        text += f.read()

    return text



def test_every_static_file_is_used():

    sources = get_own_sources()
    unused = []

    for file in get_static_files():
        if any(re.fullmatch(pattern, file) for pattern in STATIC_FILES_WITHOUT_REFERENCE):
            continue
        # Stylesheets refer to their fonts with a relative path
        if file not in sources and os.path.basename(file) not in sources:
            unused.append(file)

    assert unused == []



def test_files_of_the_pages_exist(server, boss):

    deployment = boss.create_deployment('hidden_wf')
    log = os.listdir(os.path.join(server.web_dir, 'log'))[0]
    checked = set()

    try:
        for path in ['/', '/list-objects', '/workflows', '/settings', '/settings/processing', '/settings/permissions', '/settings/security', '/settings/audit', '/settings/configuration', '/user', f"/log/{log}", f"/show_details/{deployment}", '/show_details/999999', '/docs']:
            _, _, text = boss.get(path, headers={'Accept': 'text/html'})
            urls = re.findall(r'<(?:script|img|link)\b[^>]*?\b(?:src|href)\s*=\s*["\']([^"\']+)', text, re.I)
            assert urls, path
            for url in urls:
                file = url.replace(boss.origin, '')
                if file in checked:
                    continue
                checked.add(file)
                assert file.startswith('/static/'), f"{path}: {url}"
                assert boss.get(file)[0] == 200, f"{path}: {url}"
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")

    # Images of the old pages, kept for custom templates (e.g. undo.png of the rollback example)
    for image in ['run-green.png', 'undo.png']:
        assert boss.get(f"/static/assets/img/{image}")[0] == 200



def test_one_icon_set_and_each_library_once():

    sources = get_own_sources()
    assert not re.search(r'class="[^"]*\bfa[srb]?\b|\bfa-(solid|regular|[a-z]+)\b', sources)
    assert 'fontawesome' not in sources
    assert 'popper' not in sources.replace('contains Popper', '').replace('data-bs-popper-config', '')

    with open(os.path.join(ROOT_DIR, 'webapp', 'templates', 'base.html'), encoding='utf-8') as f:
        base = f.read()

    # The base template loads the libraries of all pages; no page loads one a second time
    for directory, _, names in os.walk(os.path.join(ROOT_DIR, 'webapp', 'templates')):
        if os.path.basename(directory) == 'custom_templates':
            continue
        for name in names:
            if name == 'base.html':
                continue
            with open(os.path.join(directory, name), encoding='utf-8') as f:
                text = f.read()
            for library in ['jquery', 'sweetalert2', 'bootstrap.bundle', 'bootstrap.min.css', 'bootstrap-icons']:
                assert library not in text, f"{name}: {library} is loaded by base.html"

    for library in ['jquery.min.js', 'sweetalert2.min.js', 'sweetalert2.min.css', 'bootstrap.bundle.min.js', 'bootstrap.min.css', 'bootstrap-icons.min.css']:
        assert base.count(library) == 1, library



def test_size_of_the_static_files():

    size = {'swagger-ui': 0, 'other': 0}
    for file in get_static_files():
        size['swagger-ui' if file.startswith('assets/swagger-ui/') else 'other'] += os.path.getsize(os.path.join(STATIC_DIR, file))

    # 35 MB before the cleanup. Swagger UI is only loaded by /docs.
    assert size['other'] < 2 * 1024 * 1024
    assert size['swagger-ui'] < 2.5 * 1024 * 1024



#-----------------------------------------------------------------------------------------------
# Objects table of the deployment page (docs/bugfixes/deployment-objects-table.md)
#-----------------------------------------------------------------------------------------------

def get_objects_table(page: str) -> dict:
    """The data block of the table "Objects to deploy" """

    import html, json

    match = re.search(r'<script type="application/json" id="deployment-objects">(.*?)</script>', page, re.S)
    assert match, 'no data block of the objects'
    # tojson escapes <, >, & and ' as \\u...: nothing in the block can end it or be read as HTML
    assert '<' not in match.group(1) and "'" not in match.group(1)

    return json.loads(html.unescape(match.group(1)) if '&' in match.group(1) else match.group(1))



OBJECTS = [
    # level, name, deploy_status
    (1, 'orders', 'finished'),
    (1, 'customer', 'finished'),
    (1, "o'brien", 'new'),
    (2, 'ordersl1', 'new'),
    (2, 'orderd', 'new'),
    (3, 'ord001', 'failed'),
    (3, 'ord002', 'new'),
    (3, 'ordsrv', 'new'),
    (4, 'ordmenu', 'new'),
]


def add_objects(server, deployment: int, objects=OBJECTS) -> None:

    import sqlite3

    db = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'), timeout=10)
    for level, name, status in objects:
        db.execute("""INSERT INTO deploy_objects (meta_file_id, level, prod_lib, lib, name, type, attribute, deploy_status, ready, properties)
                      VALUES (?, ?, 'prodlib', 'devlib', ?, 'file', 'pf', ?, 1, '{}')""", (deployment, level, name, status))
    db.commit()
    db.close()



@pytest.fixture()
def objects_deployment(server, boss):

    from test_web_deployment import cancel_open_deployments

    cancel_open_deployments(boss, 'seq')
    deployment = boss.create_deployment('seq_wf')
    add_objects(server, deployment)

    yield deployment

    boss.post(f"/api/cancel_deployment/{deployment}")



def ready_of(client, deployment: int) -> dict:
    return {o['name']: bool(o['ready']) for o in client.get_deployment(deployment)['objects']}



def test_objects_table_has_one_row_per_object(boss, objects_deployment):

    _, _, text = boss.get(f"/show_details/{objects_deployment}", headers={'Accept': 'text/html'})
    table = get_objects_table(text)

    assert len(table['objects']) == len(OBJECTS)
    assert [o['level'] for o in table['objects']] == sorted(o['level'] for o in table['objects'])
    assert 'Level 1</td>' not in text

    assert 'bootstrap-table.min.css' in text
    assert 'assets/js/pages/deployment.js' in text

    for row in table['objects']:
        assert set(row) >= {'lib', 'name', 'type', 'level', 'ready', 'status', 'can_change'}



def test_objects_table_without_objects(server, boss):

    from test_web_deployment import cancel_open_deployments

    cancel_open_deployments(boss, 'seq')
    deployment = boss.create_deployment('seq_wf')

    try:
        _, _, text = boss.get(f"/show_details/{deployment}", headers={'Accept': 'text/html'})
        assert 'This deployment has no objects' in text
        assert get_objects_table(text)['objects'] == []
        assert 'id="object_list"' not in text
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_switches_which_cant_be_used_are_disabled(server, boss, objects_deployment):

    _, _, text = boss.get(f"/show_details/{objects_deployment}", headers={'Accept': 'text/html'})
    table = get_objects_table(text)

    assert table['can_change'] is True
    assert {o['name']: o['can_change'] for o in table['objects']} == {name: status != 'finished' for _, name, status in OBJECTS}
    assert 'data-objects-ready="true"' in text

    # Without the permission `run`: nothing can be changed, no buttons
    intern = server.client('intern')
    _, _, text = intern.get(f"/show_details/{objects_deployment}", headers={'Accept': 'text/html'})
    table = get_objects_table(text)
    assert table['can_change'] is False
    assert not any(o['can_change'] for o in table['objects'])
    assert 'data-objects-ready' not in text

    # Canceled deployment: nothing can be changed
    boss.post(f"/api/cancel_deployment/{objects_deployment}")
    _, _, text = boss.get(f"/show_details/{objects_deployment}", headers={'Accept': 'text/html'})
    table = get_objects_table(text)
    assert table['can_change'] is False
    assert not any(o['can_change'] for o in table['objects'])



def object_ids(*names) -> list:
    return [{'lib': 'devlib', 'name': name, 'type': 'file'} for name in names]



def test_set_objects_ready(server, boss, objects_deployment):

    history_before = len(json.loads(boss.get(f"/api/show_processing_history/{objects_deployment}")[2]))

    status, data = boss.post_json(f"/api/set_objects_ready/{objects_deployment}", {'ready': False, 'objects': object_ids('orders', "o'brien", 'ord001', 'ordmenu')})

    assert status == 200, data
    assert data['changed'] == 3
    assert data['finished'] == object_ids('orders')

    ready = ready_of(boss, objects_deployment)
    assert ready['orders'] is True          # finished: unchanged
    assert ready["o'brien"] is False
    assert ready['ord001'] is False
    assert ready['ordmenu'] is False
    assert ready['ord002'] is True          # not given

    # One entry in the processing history
    history = json.loads(boss.get(f"/api/show_processing_history/{objects_deployment}")[2])
    assert len(history) == history_before + 1
    assert '3 objects' in history[-1]['details'] or '3 objects' in history[0]['details']

    # And back
    status, data = boss.post_json(f"/api/set_objects_ready/{objects_deployment}", {'ready': True, 'objects': object_ids("o'brien", 'ord001')})
    assert status == 200 and data['changed'] == 2
    assert ready_of(boss, objects_deployment)["o'brien"] is True



def test_set_objects_ready_changes_nothing_if_an_object_is_unknown(boss, objects_deployment):

    before = ready_of(boss, objects_deployment)

    status, data = boss.post_json(f"/api/set_objects_ready/{objects_deployment}", {'ready': False, 'objects': object_ids('ord002', 'nothere')})

    assert status == 404, data
    assert 'nothere' in data['message']
    assert ready_of(boss, objects_deployment) == before



@pytest.mark.parametrize('body', [
    {},
    {'ready': True},
    {'ready': True, 'objects': []},
    {'ready': 'yes', 'objects': [{'lib': 'devlib', 'name': 'ord002', 'type': 'file'}]},
    {'ready': True, 'objects': [{'lib': 'devlib', 'name': 'ord002'}]},
    {'ready': True, 'objects': ['ord002']},
])
def test_set_objects_ready_checks_its_input(boss, objects_deployment, body):

    status, data = boss.post_json(f"/api/set_objects_ready/{objects_deployment}", body)
    assert status == 422, data



def test_set_objects_ready_needs_run(server, objects_deployment):

    intern = server.client('intern')
    status, _ = intern.post_json(f"/api/set_objects_ready/{objects_deployment}", {'ready': False, 'objects': object_ids('ord002')})
    assert status == 403



def test_set_objects_ready_in_a_canceled_deployment(boss, objects_deployment):

    boss.post(f"/api/cancel_deployment/{objects_deployment}")
    status, _ = boss.post_json(f"/api/set_objects_ready/{objects_deployment}", {'ready': False, 'objects': object_ids('ord002')})
    assert status == 409



def test_set_objects_ready_needs_post_from_the_own_origin(server, boss, objects_deployment):

    assert boss.get(f"/api/set_objects_ready/{objects_deployment}")[0] in [404, 405]

    other = server.client('boss')
    other.origin = 'http://evil.example'
    assert other.post(f"/api/set_objects_ready/{objects_deployment}", {'ready': False, 'objects': object_ids('ord002')})[0] == 403



#-----------------------------------------------------------------------------------------------
# Minor defects (docs/bugfixes/minor-web-defects.md)
#-----------------------------------------------------------------------------------------------

def test_log_page_selects_the_number_of_lines(server, boss):

    log = os.listdir(os.path.join(server.web_dir, 'log'))[0]

    for lines in [100, 500, 1000, 10000]:
        _, _, text = boss.get(f"/log/{log}/{lines}", headers={'Accept': 'text/html'})
        selected = re.findall(r'<option value="(\d+)"\s*selected', text)
        assert selected == [str(lines)], lines

    assert '<label for="number_of_lines">' in text



def test_error_page(boss):

    status, _, text = boss.get('/show_details/999999', headers={'Accept': 'text/html'})

    assert status == 404
    assert 'Deployment 999999 not found' in text
    assert 'fucking' not in text.lower()
    assert 'data-dismiss' not in text
    # The message and a link back, no form (minor defects 9 and 10). The only form is the logout button of the navigation.
    assert text.count('<form') == 1 and 'action="/logout"' in text



def test_user_page_doesnt_log_the_token():

    with open(os.path.join(ROOT_DIR, 'webapp', 'templates', 'admin', 'user.html'), encoding='utf-8') as f:
        text = f.read()

    assert 'console.' not in text
