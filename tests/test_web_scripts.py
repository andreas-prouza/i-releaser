"""Rules for scripts of the web app (docs/features/web-ui-scripts.md#rules)"""
import ast, os, re

import pytest

from web_server import ROOT_DIR, Web_Server


WEB_DIR = os.path.join(ROOT_DIR, 'webapp')
TEMPLATES_DIR = os.path.join(WEB_DIR, 'templates')
SCRIPTS_DIR = os.path.join(WEB_DIR, 'static', 'assets', 'js')

# Libraries, not own scripts
VENDOR_SCRIPTS = {'jquery.min.js', 'sweetalert2.min.js', 'prism.js'}

# Own scripts which may set HTML: only rendered parts of the server
HTML_ALLOWED = {
    'pages/deployment.js': 'the steps panel from GET /show_details/{id}/stage/{stage_id}',
}

# Python files of the web app which still build HTML as text
PYTHON_HTML_ALLOWED = {}

SCRIPT_BLOCK = re.compile(r'<script\b([^>]*)>(.*?)</script\s*>', re.I | re.S)
HANDLER = re.compile(r'<[a-zA-Z][^>]*?\son[a-z]+\s*=', re.I | re.S)
JS_URL = re.compile(r'\b(href|src|action|formaction)\s*=\s*["\']?\s*javascript:', re.I)
CONSOLE = re.compile(r'\bconsole\s*\.\s*[a-z]+\s*\(')
HTML_SINKS = re.compile(r'\.innerHTML\s*[+]?=|\.outerHTML\s*=|insertAdjacentHTML\s*\(|document\.write(ln)?\s*\(')
TAG = re.compile(r'<\s*/?\s*[a-zA-Z][a-zA-Z0-9-]*(\s[^<>]*)?/?>')



def get_templates() -> dict:
    """Relative path -> text. Templates of the installation (custom_templates) are not part of the repository."""

    templates = {}
    for directory, _, names in os.walk(TEMPLATES_DIR):
        if os.path.basename(directory) == 'custom_templates':
            continue
        for name in names:
            if name.endswith('.html'):
                path = os.path.join(directory, name)
                with open(path, encoding='utf-8') as f:
                    templates[os.path.relpath(path, TEMPLATES_DIR).replace(os.sep, '/')] = f.read()
    return templates



def get_own_scripts() -> dict:

    scripts = {}
    for directory, _, names in os.walk(SCRIPTS_DIR):
        for name in names:
            if name.endswith('.js') and name not in VENDOR_SCRIPTS:
                path = os.path.join(directory, name)
                with open(path, encoding='utf-8') as f:
                    scripts[os.path.relpath(path, SCRIPTS_DIR).replace(os.sep, '/')] = f.read()
    return scripts



def template_violations(text: str) -> list[str]:
    """The rules 1, 2 and 6 for a template"""

    # Comments of Jinja are not part of the page
    text = re.sub(r'\{#.*?#\}', '', text, flags=re.S)
    violations = []

    for attributes, content in SCRIPT_BLOCK.findall(text):
        if re.search(r'type\s*=\s*["\']application/json["\']', attributes, re.I):
            continue
        if content.strip():
            violations.append(f"1: <script> with code: {content.strip()[:60]!r}")

    violations += [f"2: handler attribute {m.group(0)[-40:]!r}" for m in HANDLER.finditer(text)]
    violations += [f"2: javascript: URL" for _ in JS_URL.finditer(text)]
    violations += [f"6: {m.group(0)!r}" for m in CONSOLE.finditer(text)]

    return violations



def test_rules_of_the_templates():
    """Without exceptions since the Content-Security-Policy (docs/features/web-ui-security-headers.md)"""

    problems = [f"{name}: {v}" for name, text in get_templates().items() for v in template_violations(text)]
    assert problems == []



def test_rule_check_finds_violations():

    assert template_violations('<script>alert(1)</script>')
    assert template_violations('<button type="button" onclick="x()">')
    assert template_violations('<img\n  src="a.png"\n  onerror="x()">')
    assert template_violations('<a href="javascript:x()">')
    assert template_violations('<p>{{ x }}</p><script>\nconsole.log(1)</script>')

    assert not template_violations('<script src="{{ url_for(\'static\', path=\'a.js\') }}"></script>')
    assert not template_violations('<script type="module" src="a.js"></script>')
    assert not template_violations('<script type="application/json" id="d">{{ data | tojson }}</script>')
    assert not template_violations('<button data-action="online-check" data-on="x">Button</button>')
    assert not template_violations('{# <script>alert(1)</script> #}')



def test_own_scripts_have_no_console_output():

    problems = [f"{name}: {m.group(0)}" for name, text in get_own_scripts().items() for m in CONSOLE.finditer(text)]
    assert problems == []



def test_own_scripts_build_no_html_from_text():

    problems = []
    for name, text in get_own_scripts().items():
        if HTML_SINKS.search(text) and name not in HTML_ALLOWED:
            problems.append(name)

    assert problems == []
    assert set(HTML_ALLOWED) <= set(get_own_scripts())



def python_files_with_html() -> dict:

    found = {}
    for top in ['routes', 'web_modules']:
        for directory, _, names in os.walk(os.path.join(WEB_DIR, top)):
            for name in names:
                if not name.endswith('.py'):
                    continue
                path = os.path.join(directory, name)
                with open(path, encoding='utf-8') as f:
                    tree = ast.parse(f.read())
                lines = [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str) and TAG.search(node.value)]
                if lines:
                    found[os.path.relpath(path, WEB_DIR).replace(os.sep, '/')] = lines
    return found



def test_python_builds_no_html():

    found = python_files_with_html()

    assert {name: lines for name, lines in found.items() if name not in PYTHON_HTML_ALLOWED} == {}
    # The list shrinks: a file of it which builds no HTML any more has to be removed from it
    assert set(PYTHON_HTML_ALLOWED) <= set(found)



#-----------------------------------------------------------------------------------------------
# Custom templates (docs/scripts.md#scripts-of-custom-templates)
#-----------------------------------------------------------------------------------------------

CUSTOM_TEMPLATE = """{% if deployment_dict['general']['status'] == 'ready' %}
<button type="button" class="btn btn-sm btn-outline-secondary" data-check data-id="{{ deployment_dict['general']['id'] }}">Check</button>
<script type="module" src="{{ url_for('static', path='custom/check.js') }}"></script>
{% endif %}
"""

CUSTOM_SCRIPT = """import { post_json } from '../assets/js/app/api.js';
document.addEventListener('click', (event) => { if (event.target.closest('[data-check]')) post_json('/api/x'); });
"""


@pytest.fixture(scope='module')
def custom_server():

    server = Web_Server()
    with open(os.path.join(server.web_dir, 'templates', 'custom_templates', 'deployment_status.html'), 'w') as f:
        f.write(CUSTOM_TEMPLATE)
    os.makedirs(os.path.join(server.web_dir, 'static', 'custom'), exist_ok=True)
    with open(os.path.join(server.web_dir, 'static', 'custom', 'check.js'), 'w') as f:
        f.write(CUSTOM_SCRIPT)

    server.start()
    yield server
    server.close()



def test_custom_template_with_a_script_file(custom_server):

    boss = custom_server.client('boss')
    deployment = boss.create_deployment('seq_wf')

    try:
        _, _, page = boss.get(f"/show_details/{deployment}", headers={'Accept': 'text/html'})
        assert f'data-check data-id="{deployment}"' in page
        assert re.search(r'<script type="module" src="[^"]*/static/custom/check\.js"></script>', page)

        status, headers, script = boss.get('/static/custom/check.js')
        assert status == 200
        assert 'javascript' in headers['content-type']
        assert script == CUSTOM_SCRIPT

        # The helper it imports
        assert boss.get('/static/assets/js/app/api.js')[0] == 200
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")
