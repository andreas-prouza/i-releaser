"""Layout of the pages, navigation, components and filters (docs/features/web-ui-layout.md)"""
import importlib.util, os, re
from datetime import datetime, timedelta
from enum import Enum
from html.parser import HTMLParser

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

from web_server import ROOT_DIR, Web_Server

from modules.meta_file_status import Meta_file_status
from modules import stage_status, cmd_status, object_status, job_status


WEB_DIR = os.path.join(ROOT_DIR, 'webapp')
TEMPLATES_DIR = os.path.join(WEB_DIR, 'templates')
HTML = {'Accept': 'text/html'}


def load_web_module(name: str):
    """Modules of webapp/web_modules without the web app"""
    spec = importlib.util.spec_from_file_location(name, os.path.join(WEB_DIR, 'web_modules', f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


status_view = load_web_module('status_view')
template_filters = load_web_module('template_filters')


@pytest.fixture(scope='module')
def server():
    s = Web_Server()

    # A custom route with its own page (docs/scripts.md#own-pages)
    with open(os.path.join(s.web_dir, 'custom', 'routes', 'layout_test_page.py'), 'w') as f:
        f.write(CUSTOM_ROUTE)
    with open(os.path.join(s.web_dir, 'templates', 'custom_templates', 'layout_test_page.html'), 'w') as f:
        f.write(CUSTOM_PAGE)

    s.start()
    yield s
    s.close()


CUSTOM_ROUTE = '''
from fastapi import Request
from index import app
from routes import routes
from web_modules import http_functions


def layout_test_page(request: Request):
    return http_functions.get_html_response(request, 'custom_templates/layout_test_page.html', sidebar=routes.get_sidebar_data(request))


app.add_api_route('/custom/layout_test_page', layout_test_page, methods=['GET'])
'''

CUSTOM_PAGE = '''{% extends 'base.html' %}
{% block title %}Own page{% endblock %}
{% block content %}<h1>Own page</h1><p id="own-content">Content of the own page</p>{% endblock %}
{% block scripts %}<script src="{{ url_for('static', path='custom/own.js') }}"></script>{% endblock %}
'''


@pytest.fixture(scope='module')
def deployment(server):
    boss = server.client('boss')
    deployment = boss.create_deployment('seq_wf', {'ticket': 'T-1'})
    yield deployment
    boss.post(f"/api/cancel_deployment/{deployment}")


@pytest.fixture(scope='module')
def log(server):
    return sorted(os.listdir(os.path.join(server.web_dir, 'log')))[0]


def get_pages(deployment: int, log: str) -> dict:
    """Path -> (title of the tab, entry of the navigation)"""
    return {
        '/': ('Deployments · seq · i-Releaser', 'deployments'),
        '/list-objects': ('Objects · i-Releaser', 'objects'),
        '/workflows': ('Workflows · i-Releaser', 'workflows'),
        '/settings': ('Settings · i-Releaser', 'settings'),
        '/user': ('My account · i-Releaser', 'user'),
        f"/log/{log}": (f"{log} · Logs · i-Releaser", 'logs'),
        f"/show_details/{deployment}": ('seq 1 · ready · i-Releaser', 'deployments'),
    }



class Page(HTMLParser):
    """What the tests need of a page: title, headings, forms, links of the navigation"""

    def __init__(self, text: str):
        super().__init__()
        self.title = ''
        self.h1 = []
        self.nested_forms = 0
        self.forms = 0
        self.current = []           # data-nav of links with aria-current="page"
        self.nav_entries = []
        self.inputs = []
        self.buttons = []
        self.in_nav = False
        self._open_forms = 0
        self._in = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'title':
            self._in = 'title'
        elif tag == 'h1':
            self._in = 'h1'
            self.h1.append('')
        elif tag == 'form':
            self.forms += 1
            if self._open_forms > 0:
                self.nested_forms += 1
            self._open_forms += 1
        elif tag == 'nav' and attrs.get('id') == 'app-nav':
            self.in_nav = True
        if 'data-nav' in attrs:
            self.nav_entries.append(attrs['data-nav'])
            # Links: aria-current. The entry `Logs` is the button of a menu: class active, the log in the menu has aria-current.
            if attrs.get('aria-current') == 'page' or 'active' in (attrs.get('class') or '').split():
                self.current.append(attrs['data-nav'])
        if tag == 'input' and attrs.get('type') != 'hidden':
            self.inputs.append(attrs.get('name'))
        if tag == 'button':
            self.buttons.append(attrs)

    def handle_endtag(self, tag):
        if tag == 'form':
            self._open_forms -= 1
        if tag in ('title', 'h1'):
            self._in = None

    def handle_data(self, data):
        if self._in == 'title':
            self.title += data
        elif self._in == 'h1':
            self.h1[-1] += data



def get_page(client, path: str) -> tuple[int, Page, str]:
    status, _, text = client.get(path, headers=HTML)
    return status, Page(text), text



#-----------------------------------------------------------------------------------------------
# Pages
#-----------------------------------------------------------------------------------------------

def test_every_page_has_a_title_and_one_h1(server, deployment, log):

    boss = server.client('boss')

    for path, (title, _) in get_pages(deployment, log).items():
        status, page, _ = get_page(boss, path)
        assert status == 200, path
        assert page.title.strip() == title, path
        assert len(page.h1) == 1, f"{path}: {page.h1}"
        assert page.h1[0].strip(), path

    status, page, _ = get_page(boss, '/show_details/999999')
    assert status == 404
    assert page.title.strip() == 'Not Found · i-Releaser'
    assert [h.strip() for h in page.h1] == ['Not Found']

    status, page, _ = get_page(server.client(), '/')
    assert page.title.strip() == 'Log in · i-Releaser'
    assert len(page.h1) == 1



def test_active_entry_of_the_navigation(server, deployment, log):

    boss = server.client('boss')

    for path, (_, entry) in get_pages(deployment, log).items():
        _, page, _ = get_page(boss, path)
        assert page.current == [entry], path

    # The parameter of old links is ignored
    _, page, _ = get_page(boss, '/?sidebar_active=workflows')
    assert page.current == ['deployments']

    # The active log is marked in the menu of the logs
    _, _, text = get_page(boss, f"/log/{log}")
    assert re.search(rf'<a class="dropdown-item active" href="/log/{re.escape(log)}" aria-current="page">', text)



def test_links_have_no_sidebar_parameter():

    for directory, _, names in os.walk(TEMPLATES_DIR):
        for name in names:
            with open(os.path.join(directory, name), encoding='utf-8') as f:
                assert 'sidebar_active' not in f.read(), name



def test_settings_and_logs_only_for_admins(server, deployment, log):

    _, page, _ = get_page(server.client('boss'), '/')
    assert page.nav_entries == ['deployments', 'objects', 'workflows', 'settings', 'permissions', 'logs', 'user', 'logout']

    for user in ['intern', 'runner']:
        _, page, text = get_page(server.client(user), '/')
        assert page.nav_entries == ['deployments', 'objects', 'workflows', 'user', 'logout'], user
        assert f"/log/{log}" not in text



def test_projects_are_not_in_the_navigation(server):

    _, _, text = get_page(server.client('boss'), '/workflows')
    nav = text.split('id="app-nav"', 1)[1].split('</nav>', 1)[0]
    assert '/project/' not in nav



def test_no_form_inside_a_form(server, deployment, log):

    with open(os.path.join(TEMPLATES_DIR, 'base.html'), encoding='utf-8') as f:
        assert '<form' not in f.read()

    boss = server.client('boss')
    for path in list(get_pages(deployment, log)) + ['/show_details/999999']:
        _, page, _ = get_page(boss, path)
        assert page.nested_forms == 0, path

    _, page, _ = get_page(server.client(), '/')
    assert page.forms == 1 and page.nested_forms == 0



def test_login_page(server):

    status, page, text = get_page(server.client(), '/workflows')

    assert status == 200
    assert page.inputs == ['user', 'password']
    assert [b.get('type') for b in page.buttons] == ['submit']
    assert 'id="app-nav"' not in text
    assert 'autocomplete="username"' in text and 'autocomplete="current-password"' in text
    assert 'action="/login?next=/workflows"' in text
    for old in ['Remember me', 'Forgot', 'Cancel', '</b></h1>']:
        assert old not in text, old



def test_login_opens_the_page_it_was_shown_for(server):

    client = server.client()
    status, headers, _ = client.request('POST', '/login?next=%2Fworkflows%3Fx%3D1', form={'user': 'boss', 'password': 'x'}, headers=HTML)

    assert status == 303
    assert headers['location'] == '/workflows?x=1'
    assert client.get('/workflows', headers=HTML)[0] == 200



@pytest.mark.parametrize('target', ['https://evil.example/', '//evil.example/', '/\\evil.example', 'javascript:alert(1)', '/login', '/logout', '/x\r\nSet-Cookie: a=b'])
def test_login_redirects_only_to_pages_of_the_web_app(server, target):

    status, headers, _ = server.client().request('POST', '/login?' + __import__('urllib.parse').parse.urlencode({'next': target}), form={'user': 'boss', 'password': 'x'}, headers=HTML)

    assert status == 303
    assert headers['location'] == '/'



def test_error_page(server):

    status, page, text = get_page(server.client('boss'), '/show_details/999999')

    assert status == 404
    assert 'Deployment 999999 not found' in text
    assert 'href="/"' in text
    assert page.forms == 0
    for old in ['Back to overview', 'fucking', 'data-dismiss']:
        assert old not in text, old
    # The navigation for a logged-in user
    assert 'id="app-nav"' in text



def test_custom_route_with_a_page(server):

    status, page, text = get_page(server.client('boss'), '/custom/layout_test_page')

    assert status == 200
    assert page.title.strip() == 'Own page · i-Releaser'
    assert 'Content of the own page' in text
    assert '/static/custom/own.js' in text
    assert 'id="app-nav"' in text
    assert page.current == []



#-----------------------------------------------------------------------------------------------
# Components
#-----------------------------------------------------------------------------------------------

STATUS_CLASSES = [Meta_file_status, stage_status.Status, cmd_status.Status, object_status.Status, job_status.Status]


@pytest.mark.parametrize('status', [s for cls in STATUS_CLASSES for s in cls], ids=lambda s: f"{type(s).__module__}.{s.value}")
def test_every_status_has_a_view(status):

    view = status_view.get_status_view(status)

    assert view.value == status.value
    assert view.kind in status_view.KINDS
    assert view.icon and view.icon != status_view.UNKNOWN_ICON
    assert view.text



def test_unknown_status_is_neutral():

    assert status_view.get_status_view('exploded') == status_view.Status_View(value='exploded', kind='neutral', icon=status_view.UNKNOWN_ICON, text='exploded')
    assert status_view.get_status_view(None).text == '–'
    assert status_view.get_status_view('FAILED').kind == 'danger'



@pytest.fixture(scope='module')
def jinja():
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape(['html']))
    env.filters.update(template_filters.FILTERS)
    env.globals['status_view'] = status_view.get_status_view
    return env


def render(jinja, source: str, **context) -> str:
    return jinja.from_string("{% from 'components/ui.html' import page_header, status_pill, icon_button, kv_list, section, empty_state, code_block %}" + source).render(**context)



def test_status_pill(jinja):

    for cls in STATUS_CLASSES:
        for status in cls:
            view = status_view.get_status_view(status)
            html = render(jinja, '{{ status_pill(s) }}', s=status)
            assert f'class="ir-pill k-{view.kind}"' in html
            assert f'bi-{view.icon}' in html
            assert html.endswith(f"{view.text}</span>")

    assert 'k-neutral' in render(jinja, '{{ status_pill("<b>x</b>") }}')
    assert '<b>' not in render(jinja, '{{ status_pill("<b>x</b>") }}')
    assert 'ir-spin' in render(jinja, '{{ status_pill("in process") }}')



def test_page_header(jinja):

    html = render(jinja, "{% call page_header('erp · Version 6', breadcrumb=[('Deployments', '/'), ('<erp>', '/project/erp'), ('Version 6', None)], meta='m', status='failed') %}<button>A</button>{% endcall %}")

    assert html.count('<h1>') == 1
    assert '<h1>erp · Version 6</h1>' in html
    assert '<a href="/">Deployments</a>' in html
    assert '&lt;erp&gt;' in html
    assert '<span aria-current="page">Version 6</span>' in html
    assert 'k-danger' in html
    assert '<div class="ir-page-actions"><button>A</button></div>' in html

    html = render(jinja, "{{ page_header('Objects') }}")
    assert 'ir-page-actions' not in html and 'Breadcrumb' not in html



def test_other_components(jinja):

    html = render(jinja, "{{ icon_button('trash', 'Delete <token>', {'data-id': 5}) }}")
    assert 'aria-label="Delete &lt;token&gt;"' in html and 'data-id="5"' in html and 'type="button"' in html

    html = render(jinja, "{{ kv_list([('Remote dir', None), ('Library', 'LIB<1>')], mono=['Library']) }}")
    assert '<dd>–</dd>' in html and '<dd class="ir-mono">LIB&lt;1&gt;</dd>' in html

    html = render(jinja, "{% call(part) section('Objects', has_actions=True) %}{% if part == 'actions' %}ACT{% else %}BODY{% endif %}{% endcall %}")
    assert '<div class="ir-section-actions">ACT</div>' in html and 'BODY' in html and '<h2 id="objects-title">Objects</h2>' in html

    assert 'This deployment has no objects' in render(jinja, "{{ empty_state('This deployment has no objects') }}")

    html = render(jinja, "{{ code_block('echo <x>', 'json') }}")
    assert 'class="language-json">echo &lt;x&gt;</code>' in html and 'data-copy' in html



#-----------------------------------------------------------------------------------------------
# Filters
#-----------------------------------------------------------------------------------------------

def test_datetime_filter():

    f = template_filters.format_datetime
    assert f(datetime(2026, 11, 16, 18, 56, 47, 123456)) == '2026-11-16 18:56:47'
    assert f('2026-11-16 18:56:47.742883') == '2026-11-16 18:56:47'
    assert f('2026-11-16T18:56:47') == '2026-11-16 18:56:47'
    assert f(None) == '–' and f('') == '–'
    assert f('not a time') == 'not a time'



@pytest.mark.parametrize('value, text', [
    (1.234, '1.2 s'), (0, '0.0 s'), (42.7, '42 s'), (60, '1 min'), (190, '3 min 10 s'),
    (3600, '1 h'), (7500, '2 h 5 min'), (timedelta(seconds=75), '1 min 15 s'), (None, '–'), (-1, '–'),
])
def test_duration_filter(value, text):
    assert template_filters.format_duration(value) == text



def test_or_dash_filter():

    f = template_filters.or_dash
    assert [f(v) for v in [None, '', '  ', [], {}]] == ['–'] * 5
    assert [f(v) for v in [0, False, 'x', [1]]] == [0, False, 'x', [1]]



#-----------------------------------------------------------------------------------------------
# Styles
#-----------------------------------------------------------------------------------------------

def read_tokens() -> dict:
    """Colours of the two themes in app.css"""

    with open(os.path.join(WEB_DIR, 'static', 'assets', 'css', 'app.css'), encoding='utf-8') as f:
        css = f.read()

    light = re.search(r':root,\s*\[data-bs-theme=light\]\s*\{(.*?)\}', css, re.S).group(1)
    dark = re.search(r'\n\[data-bs-theme=dark\]\s*\{(.*?)\}', css, re.S).group(1)

    def colours(block: str) -> dict:
        return dict(re.findall(r'--ir-([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})', block))

    tokens = {'light': colours(light)}
    tokens['dark'] = {**tokens['light'], **colours(dark)}
    return tokens



def contrast(a: str, b: str) -> float:

    def luminance(colour: str) -> float:
        channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    high, low = sorted([luminance(a), luminance(b)], reverse=True)
    return (high + 0.05) / (low + 0.05)



def mix(colour: str, background: str, share: float) -> str:
    """color-mix(in srgb, colour share, background)"""
    parts = [round(int(colour[i:i + 2], 16) * share + int(background[i:i + 2], 16) * (1 - share)) for i in (1, 3, 5)]
    return '#' + ''.join(f"{p:02x}" for p in parts)



@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_contrast_of_text_and_status_colours(theme):

    t = read_tokens()[theme]

    for text in ['text', 'muted', 'link']:
        for background in ['bg', 'surface', 'surface-2']:
            assert contrast(t[text], t[background]) >= 4.5, f"{theme}: {text} on {background}"

    assert contrast(t['primary-text'], t['primary']) >= 4.5
    assert contrast(t['nav-text'], t['nav-bg']) >= 4.5
    assert contrast(t['nav-text'], t['nav-active']) >= 4.5

    # The text of a status pill on its own tint (12 %), on the page and on a card
    for kind in status_view.KINDS:
        for background in ['bg', 'surface']:
            assert contrast(t[kind], mix(t[kind], t[background], 0.12)) >= 4.5, f"{theme}: {kind} on {background}"
