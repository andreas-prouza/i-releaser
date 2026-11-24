"""Live updates of the deployment page in a real browser (docs/features/web-ui-live-updates.md)

Skipped if Playwright or its Chromium is not installed, see tests/browser_tools.py.
"""
import os, sqlite3

import pytest

from browser_tools import open_page, wait_until
from test_deployment_page import PAGE_USERS, PAGE_WORKFLOWS
from web_server import Client, Web_Server


pytestmark = pytest.mark.browser

LIVE_MS = 20000


@pytest.fixture(scope='module')
def server(browser):
    """Started after `browser`: without Playwright the module is skipped before the web app is started"""
    s = Web_Server(workflows=PAGE_WORKFLOWS, users=PAGE_USERS).start()
    yield s
    s.close()


@pytest.fixture()
def boss(server):
    return server.client('boss')


def fresh(boss, workflow: str = 'seq_wf') -> int:
    from test_web_deployment import cancel_open_deployments
    cancel_open_deployments(boss, PAGE_WORKFLOWS[workflow]['default_project'])
    return boss.create_deployment(workflow, {'ticket': 'T-1'})


def add_objects(server, deployment: int, count: int) -> None:
    db = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'), timeout=10)
    for i in range(count):
        db.execute("""INSERT INTO deploy_objects (meta_file_id, level, prod_lib, lib, name, type, attribute, deploy_status, ready, properties)
                      VALUES (?, ?, 'prodlib', 'devlib', ?, 'pgm', 'rpgle', 'new', 1, '{}')""", (deployment, 1 + i // 10, f"obj{i:02}"))
    db.commit()
    db.close()


def wait_for_state(page, stage_id: int, state: str) -> None:
    wait_until(page, f"document.querySelector('.ir-flow-node[data-stage-id=\"{stage_id}\"]').dataset.state === '{state}'", timeout=LIVE_MS)



def test_run_a_stage_without_loading_the_page(server, browser_context, boss):

    deployment = fresh(boss)
    stages = boss.get_stages(deployment)
    try:
        page, watch = open_page(browser_context, server, f"/show_details/{deployment}")
        page.evaluate("window.not_loaded_again = 42")
        page.locator('[data-action="toggle-steps"]').click()

        page.locator('.ir-attention [data-action="run-stage"]').click()
        page.locator('.swal2-confirm').click()
        page.wait_for_selector('.swal2-toast')

        wait_for_state(page, stages['START']['id'], 'finished')
        wait_until(page, "document.querySelector('.ir-attention-text').textContent.includes('PROD')", timeout=LIVE_MS)
        wait_until(page, "document.querySelector('#stage-steps .ir-step').dataset.status === 'finished'", timeout=LIVE_MS)
        assert 'ready' in page.title()

        # The same page: nothing was loaded again, the steps are still open
        assert page.evaluate("window.not_loaded_again") == 42
        assert page.locator('#stage-steps-body').is_visible()

        watch.assert_clean()
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_table_filter_page_and_open_step_survive_a_change(server, browser_context, boss):

    deployment = fresh(boss)
    add_objects(server, deployment, 25)
    stages = boss.get_stages(deployment)
    try:
        page, watch = open_page(browser_context, server, f"/show_details/{deployment}")
        page.locator('[data-action="toggle-steps"]').click()
        page.locator('#stage-steps [data-action="toggle-step"]').first.click()

        # The objects: page 2
        page.locator('.page-link[aria-label="to page 2"]').click()
        assert page.locator('#object_list tbody tr').first.inner_text().count('obj10') == 1
        page.evaluate("window.scrollTo(0, 400)")
        scroll = page.evaluate("window.scrollY")

        # Changes of others: an object, and a stage
        boss.post(f"/api/set_source_ready_4_deployment/{deployment}", {'lib': 'devlib', 'name': 'obj12', 'type': 'pgm', 'checked': False})
        wait_until(page, "!document.querySelector('#object_list tbody tr:nth-child(3) .obj-ready').checked", timeout=LIVE_MS)
        assert page.locator('section[aria-labelledby="objects-title"] .page-item.active').inner_text() == '2'

        boss.run_stage(deployment, 'START')
        wait_for_state(page, stages['START']['id'], 'finished')

        assert page.locator('section[aria-labelledby="objects-title"] .page-item.active').inner_text() == '2'
        assert page.locator('#stage-steps [data-action="toggle-step"]').first.get_attribute('aria-expanded') == 'true'
        assert page.evaluate("window.scrollY") == scroll

        # A filter stays too
        page.select_option('.bootstrap-table-filter-control-level', '3')
        wait_until(page, "$('#object_list').bootstrapTable('getData').length === 5")
        assert page.locator('#object_list tbody tr').count() == 5
        boss.post(f"/api/set_source_ready_4_deployment/{deployment}", {'lib': 'devlib', 'name': 'obj21', 'type': 'pgm', 'checked': False})
        wait_until(page, "!document.querySelector('#object_list tbody tr:nth-child(2) .obj-ready').checked", timeout=LIVE_MS)
        assert page.locator('#object_list tbody tr').count() == 5
        assert page.locator('.bootstrap-table-filter-control-level').input_value() == '3'

        watch.assert_clean()
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_log_dialog_stays_open_during_a_change(server, browser_context, boss):

    deployment = fresh(boss)
    stages = boss.get_stages(deployment)
    boss.run_stage(deployment, 'START')
    boss.wait_for_stage(deployment, 'START')
    try:
        page, watch = open_page(browser_context, server, f"/show_details/{deployment}#stage={stages['START']['id']}")
        wait_until(page, "document.querySelector('#stage-steps h2').textContent === 'START'")
        page.locator('#stage-steps [data-action="show-log"]').first.click()
        page.wait_for_selector('#log-dialog.show')

        boss.run_stage(deployment, 'PROD')
        wait_for_state(page, stages['PROD']['id'], 'finished')
        assert page.locator('#log-dialog').is_visible()
        assert 'quick' in page.locator('#log-text').inner_text()

        watch.assert_clean()
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_reconnect_after_a_restart_of_the_web_app(server, browser_context, boss):

    deployment = fresh(boss)
    stages = boss.get_stages(deployment)
    try:
        page, watch = open_page(browser_context, server, f"/show_details/{deployment}")
        page.evaluate("window.not_loaded_again = 42")

        server.stop()
        page.wait_for_selector('.ir-reconnecting', state='visible', timeout=LIVE_MS)

        # A change while the page has no connection
        server.start()
        boss.run_stage(deployment, 'START')
        boss.wait_for_stage(deployment, 'START')

        page.wait_for_selector('.ir-reconnecting', state='hidden', timeout=40000)
        wait_for_state(page, stages['START']['id'], 'finished')
        assert page.evaluate("window.not_loaded_again") == 42

        # The failed requests while the web app was down are expected
        watch.assert_clean(allow=('/api/watch_state/', '/show_details/', 'net::ERR_CONNECTION_REFUSED'))
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_ended_session_is_shown(server, browser_context, boss):

    deployment = fresh(boss)
    try:
        page, watch = open_page(browser_context, server, f"/show_details/{deployment}")

        # The session of the page ends (logged out in another tab)
        session_id = [c['value'] for c in browser_context.cookies() if c['name'] == 'session_id'][0]
        other_tab = Client(server)
        other_tab.session_id = session_id
        other_tab.post('/logout')

        # A change: the page loads its parts and gets 401
        boss.run_stage(deployment, 'START')
        wait_until(page, "Swal.getTitle() && Swal.getTitle().textContent === 'Your session has ended'", timeout=LIVE_MS)

        watch.assert_clean(allow=('401',))
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")
