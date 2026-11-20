"""Security headers and the Content-Security-Policy (docs/features/web-ui-security-headers.md)"""
import os, re

import pytest

from web_server import ROOT_DIR, Web_Server


CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; "
       "connect-src 'self'; media-src 'none'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")

HTML = {'Accept': 'text/html'}


@pytest.fixture(scope='module')
def server():
    s = Web_Server().start()
    yield s
    s.close()


def check_common(headers: dict, what: str) -> None:
    assert headers.get('x-content-type-options') == 'nosniff', what
    assert headers.get('referrer-policy') == 'same-origin', what
    assert headers.get('x-frame-options') == 'DENY', what



def test_headers_of_every_kind_of_response(server):

    boss = server.client('boss')
    deployment = boss.create_deployment('hidden_wf')
    try:
        responses = {
            'page': boss.get('/workflows', headers=HTML),
            'deployment page': boss.get(f"/show_details/{deployment}", headers=HTML),
            'part of a page': boss.get(f"/show_details/{deployment}/stage/{boss.get_stages(deployment)['START']['id']}", headers=HTML),
            'login page': server.client().get('/', headers=HTML),
            'error page': boss.get('/show_details/999999', headers=HTML),
            'docs': boss.get('/docs', headers=HTML),
        }
        for what, (status, headers, _) in responses.items():
            check_common(headers, what)
            assert headers.get('content-security-policy') == CSP, what
            assert 'content-security-policy-report-only' not in headers, what

        for what, (status, headers, _) in {'JSON': boss.get('/api/get_workflows'), 'static file': boss.get('/static/assets/css/app.css'),
                                           'JSON error': boss.get('/api/get_meta_file_json/999999')}.items():
            check_common(headers, what)
            assert 'content-security-policy' not in headers, what
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_docs_without_inline_script(server):

    status, _, text = server.client('boss').get('/docs', headers=HTML)
    assert status == 200
    for attributes, content in re.findall(r'<script\b([^>]*)>(.*?)</script>', text, re.S):
        assert 'src=' in attributes and not content.strip()
    assert '/static/assets/js/swagger-init.js' in text



def test_report_only():

    s = Web_Server(settings="C_CSP_REPORT_ONLY = True\n").start()
    try:
        _, headers, _ = s.client('boss').get('/workflows', headers=HTML)
        assert headers.get('content-security-policy-report-only') == CSP
        assert 'content-security-policy' not in headers
        assert 'C_CSP_REPORT_ONLY is set' in s.read_logs()
    finally:
        s.close()



def test_old_global_functions_are_gone():

    web_dir = os.path.join(ROOT_DIR, 'webapp')
    assert not os.path.exists(os.path.join(web_dir, 'static', 'assets', 'js', 'web.deploy.js'))

    for top in ['templates', os.path.join('static', 'assets', 'js')]:
        for directory, _, names in os.walk(os.path.join(web_dir, top)):
            if os.path.basename(directory) == 'custom_templates':
                continue
            for name in names:
                if name.endswith(('.html', '.js')) and not name.endswith('.min.js') and name not in ('prism.js', 'swagger-ui-bundle.js'):
                    with open(os.path.join(directory, name), encoding='utf-8') as f:
                        text = f.read()
                    assert not re.search(r'\b(postData|async_postData|http_post|http_get|http_getData)\s*\(', text), name
                    assert 'web.deploy.js' not in text, name
