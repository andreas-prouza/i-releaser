"""The admin pages in a real browser (docs/features/web-ui-admin-pages.md, acceptance criteria "Browser tests")

Skipped if Playwright or its Chromium is not installed, see tests/browser_tools.py.
"""
import os

import pytest

from browser_tools import open_page, wait_until
from web_server import Client, Web_Server


pytestmark = pytest.mark.browser


@pytest.fixture(scope='module')
def server(browser):
    """Started after `browser`: without Playwright the module is skipped before the web app is started"""
    s = Web_Server().start()
    yield s
    s.stop_service()
    s.close()



def test_processing_mode_and_service_without_loading_the_page(server, browser_context):

    page, watch = open_page(browser_context, server, '/settings/processing')
    page.evaluate("window.not_loaded_again = 42")

    try:
        page.locator('#processing-mode').select_option('service')
        page.locator('[data-action="set-processing-mode"]').click()
        assert page.locator('.swal2-title').inner_text() == 'The processing service is not running'
        page.locator('.swal2-confirm').click()

        # The output of the service script, then the part of the page is current
        wait_until(page, "Swal.getTitle() && Swal.getTitle().textContent === 'Processing service: start'", timeout=30000)
        page.locator('.swal2-confirm').click()
        page.wait_for_selector('[data-service="running"]', timeout=20000)
        assert page.locator('#processing-mode').input_value() == 'service'
        assert page.locator('[data-action="processing-service"][data-command="start"]').is_disabled()
        assert page.evaluate("window.not_loaded_again") == 42

        watch.assert_clean()
    finally:
        boss = server.client('boss')
        boss.post_json('/api/processing_service/stop')
        boss.post_json('/api/set_processing_mode/thread')



def test_filter_a_log_by_level_and_text(server, browser_context):

    log = sorted(os.listdir(os.path.join(server.web_dir, 'log')))[0]
    # A warning in the log: a stage which waits for the processing service
    boss = server.client('boss')
    boss.post_json('/api/set_processing_mode/service')
    deployment = boss.create_deployment('hidden_wf')
    boss.run_stage(deployment, 'START')
    boss.post(f"/api/cancel_deployment/{deployment}")
    boss.post_json('/api/set_processing_mode/thread')

    page, watch = open_page(browser_context, server, f"/log/{log}/1000")
    total = page.locator('.ir-log-line').count()

    page.locator('#log-level').select_option('WARNING')
    visible = page.locator('.ir-log-line:not([hidden])')
    assert 0 < visible.count() < total
    assert set(visible.evaluate_all("lines => lines.map(l => l.dataset.level)")) <= {'WARNING', 'ERROR', 'CRITICAL'}
    assert page.url.endswith('?level=WARNING')

    page.locator('#log-search').fill('Processing service is not running')
    assert all('Processing service is not running' in line for line in visible.all_inner_texts())
    assert visible.count() >= 1

    # Another number of lines keeps the filter
    with page.expect_navigation():
        page.locator('#number_of_lines').select_option('500')
    assert '/500?level=WARNING&q=' in page.url
    assert page.locator('#log-level').input_value() == 'WARNING'

    watch.assert_clean()



def test_admin_revokes_the_token_of_a_user_on_the_security_tab(server, browser_context):
    """The actions of the security tab run with pages/security.js (docs/features/web-ui-admin-pages.md#decisions-2026-11-24)"""

    status, created = server.client('runner').post_json('/api/v2/tokens', {'name': 'Revoke test', 'scope': 'read'})
    assert status == 201, created
    bearer = {'Authorization': f"Bearer {created['token']}"}
    assert Client(server).get('/api/v2/workflows', headers=bearer)[0] == 200

    page, watch = open_page(browser_context, server, '/settings/security')
    page.locator('[data-action="revoke-token"][data-name="Revoke test"]').click()
    assert page.locator('.swal2-title').inner_text() == 'Revoke the API token Revoke test of runner?'
    with page.expect_navigation():
        page.locator('.swal2-confirm').click()
    page.wait_for_selector('.swal2-toast')

    assert 'Token Revoke test of runner revoked' in page.locator('.swal2-toast').inner_text()
    assert page.locator('[data-action="revoke-token"][data-name="Revoke test"]').count() == 0
    assert Client(server).get('/api/v2/workflows', headers=bearer)[0] == 401
    watch.assert_clean()



def test_change_and_reset_a_setting_in_the_form(server, browser_context):
    """docs/features/settings-in-web-app.md: pages/configuration.js sends the value with its type"""

    page, watch = open_page(browser_context, server, '/settings/configuration')
    row = page.locator('tr[data-setting="C_RETENTION_DAYS"]')

    row.locator('[data-setting-input]').fill('45')
    with page.expect_navigation():
        row.locator('[data-action="save-setting"]').click()
    page.wait_for_selector('.swal2-toast')
    assert 'C_RETENTION_DAYS saved' in page.locator('.swal2-toast').inner_text()
    row = page.locator('tr[data-setting="C_RETENTION_DAYS"]')
    assert row.locator('[data-setting-input]').input_value() == '45'
    assert 'web app' in row.inner_text()

    # A switch: True or False, not a text
    archive = page.locator('tr[data-setting="C_RETENTION_ARCHIVE"]')
    archive.locator('[data-setting-input]').check()
    with page.expect_navigation():
        archive.locator('[data-action="save-setting"]').click()
    page.wait_for_selector('.swal2-toast')
    assert page.locator('tr[data-setting="C_RETENTION_ARCHIVE"] [data-setting-input]').is_checked()

    for name in ['C_RETENTION_DAYS', 'C_RETENTION_ARCHIVE']:
        page.locator(f'tr[data-setting="{name}"] [data-action="reset-setting"]').click()
        with page.expect_navigation():
            page.locator('.swal2-confirm').click()
        page.wait_for_selector('.swal2-toast')

    assert page.locator('tr[data-setting="C_RETENTION_DAYS"] [data-setting-input]').input_value() == '0'
    assert page.locator('[data-action="reset-setting"]').count() == 0
    watch.assert_clean()



def test_token_generate_copy_use_and_delete(server, browser):

    context = browser.new_context()
    context.grant_permissions(['clipboard-read', 'clipboard-write'])
    try:
        page, watch = open_page(context, server, '/user')

        page.locator('[data-action="new-token"]').click()
        page.locator('#token-name').fill('Copy test')
        page.locator('#token-scope').select_option('read')
        page.locator('.swal2-confirm').click()
        wait_until(page, "Swal.getTitle() && Swal.getTitle().textContent === 'Token Copy test created'")
        assert "can't be shown again" in page.locator('.swal2-html-container').inner_text()

        page.locator('.swal2-html-container [data-copy]').click()
        wait_until(page, "document.querySelector('.swal2-html-container [data-copy]').title === 'Copied'")
        token = page.evaluate("navigator.clipboard.readText()")
        assert token == page.locator('.swal2-html-container code').inner_text() and len(token) > 20

        # The token works for the Web API, only to read (scope read)
        api = Client(server)
        assert api.get('/api/v2/workflows', headers={'Authorization': f"Bearer {token}"})[0] == 200
        assert api.request('POST', '/api/v2/deployments', body={'workflow': 'seq_wf'}, headers={'Authorization': f"Bearer {token}"})[0] == 403

        with page.expect_navigation():
            page.locator('.swal2-confirm').click()
        assert 'Copy test' in page.locator('.ir-tokens').inner_text()
        page.locator('[data-action="delete-token"][data-name="Copy test"]').click()
        with page.expect_navigation():
            page.locator('.swal2-confirm').click()
        page.wait_for_selector('.swal2-toast')

        assert Client(server).get('/api/get_workflows', headers={'Authorization': f"Bearer {token}"})[0] == 401
        watch.assert_clean()
    finally:
        context.close()
