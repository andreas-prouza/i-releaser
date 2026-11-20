"""The deployment page in a real browser (docs/features/web-ui-deployment-page.md, acceptance criteria "Browser tests")

Skipped if Playwright or its Chromium is not installed, see tests/browser_tools.py.
"""
import os, time

import pytest

from browser_tools import open_page, wait_until
from test_deployment_page import PAGE_USERS, PAGE_WORKFLOWS, SUB_SCRIPT, step
from web_server import Web_Server


pytestmark = pytest.mark.browser


WORKFLOWS = {
    **PAGE_WORKFLOWS,
    'many_wf': {
        'name': 'many_wf', 'default_project': 'many',
        'step_action': [step(f"s{i:03}", f"echo step {i}") for i in range(120)],
        'stages': [
            {'name': 'START', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': [f"s{i:03}" for i in range(120)]},
            {'name': 'END'},
        ],
    },
}



@pytest.fixture(scope='module')
def server(browser):
    """Started after `browser`: without Playwright the module is skipped before the web app is started"""
    s = Web_Server(workflows=WORKFLOWS, users=PAGE_USERS)
    with open(os.path.join(s.directory, 'scripts', 'page_subs.py'), 'w') as f:
        f.write(SUB_SCRIPT)
    s.start()
    yield s
    s.close()


@pytest.fixture()
def boss(server):
    return server.client('boss')


def fresh(boss, workflow: str) -> int:
    from test_web_deployment import cancel_open_deployments
    cancel_open_deployments(boss, WORKFLOWS[workflow]['default_project'])
    return boss.create_deployment(workflow, {'ticket': 'T-1'} if workflow in ('fail_wf', 'seq_wf') else None)


def run(boss, deployment: int, stage: str) -> dict:
    assert boss.run_stage(deployment, stage)[0] == 200
    return boss.wait_for_stage(deployment, stage, timeout=60)


@pytest.fixture(scope='module')
def failed(server):
    boss = server.client('boss')
    deployment = fresh(boss, 'fail_wf')
    run(boss, deployment, 'START')
    assert run(boss, deployment, 'DEPLOY')['status'] == 'failed'
    return deployment


def panel_title(page) -> str:
    return page.locator('#stage-steps h2').inner_text()


def steps_open(page) -> bool:
    return page.locator('#stage-steps-body').is_visible()



def test_select_a_stage_and_keep_it_after_a_reload(server, browser_context, boss):

    deployment = fresh(boss, 'seq_wf')
    try:
        page, watch = open_page(browser_context, server, f"/show_details/{deployment}")

        # Without a problem the steps are closed: START is ready
        assert panel_title(page) == 'START'
        assert not steps_open(page)

        page.locator('.ir-flow-node', has_text='PROD').click()
        wait_until(page, "document.querySelector('#stage-steps h2').textContent === 'PROD'")
        assert steps_open(page)
        prod_id = boss.get_stages(deployment)['PROD']['id']
        assert page.url.endswith(f"#stage={prod_id}")
        assert page.locator('.ir-flow-node.selected').get_attribute('data-stage-id') == str(prod_id)

        page.reload(wait_until='networkidle')
        wait_until(page, "document.querySelector('#stage-steps h2').textContent === 'PROD'")
        assert steps_open(page)
        assert page.locator('.ir-flow-node.selected').get_attribute('data-stage-id') == str(prod_id)

        page.locator('[data-action="toggle-steps"]').click()
        assert not steps_open(page)

        watch.assert_clean()
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_failed_deployment_opens_at_the_failed_step(server, browser_context, boss, failed):

    page, watch = open_page(browser_context, server, f"/show_details/{failed}")

    assert panel_title(page) == 'DEPLOY'
    assert steps_open(page)
    broken = page.locator('.ir-step[data-status="failed"]')
    assert broken.locator('[data-action="toggle-step"]').get_attribute('aria-expanded') == 'true'
    assert broken.locator('.ir-step-detail').is_visible()

    # Scrolled to it: in the visible part of the panel
    body = page.locator('#stage-steps-body').bounding_box()
    row = broken.bounding_box()
    assert body['y'] <= row['y'] < body['y'] + body['height']

    watch.assert_clean()



def test_finished_deployment_opens_with_closed_steps(server, browser_context, boss):

    deployment = fresh(boss, 'seq_wf')
    boss.finish_deployment(deployment)

    page, watch = open_page(browser_context, server, f"/show_details/{deployment}")
    assert panel_title(page) == 'PROD'
    assert not steps_open(page)
    assert page.locator('.ir-attention').count() == 0

    watch.assert_clean()



def test_stage_with_many_steps(server, browser_context, boss):

    deployment = fresh(boss, 'many_wf')
    run(boss, deployment, 'START')

    page, watch = open_page(browser_context, server, f"/show_details/{deployment}")
    page.locator('[data-action="toggle-steps"]').click()

    # 120 finished steps are folded into one row
    assert page.locator('.ir-step-fold > summary').inner_text() == '120 finished steps'
    page.locator('.ir-step-fold > summary').click()

    # The panel scrolls inside, the page doesn't get longer
    scroll = page.evaluate("(() => { const b = document.getElementById('stage-steps-body'); return [b.scrollHeight, b.clientHeight, innerHeight]; })()")
    assert scroll[0] > scroll[1]
    assert scroll[1] <= 0.71 * scroll[2]

    page.locator('[data-action="filter-steps"]').fill('s11')
    visible = page.locator('.ir-step:not(.ir-filtered)')
    assert visible.count() == 10
    assert visible.first.locator('.ir-step-name').inner_text() == 's110'

    page.locator('[data-action="filter-steps"]').fill('')
    page.locator('[data-action="only-problems"]').check()
    assert page.locator('.ir-step:not(.ir-filtered)').count() == 0
    assert page.locator('.ir-steps-body > .ir-steps-nothing').is_visible()

    watch.assert_clean()



def test_run_a_stage_one_dialog_one_toast(server, browser_context, boss):

    deployment = fresh(boss, 'seq_wf')
    try:
        page, watch = open_page(browser_context, server, f"/show_details/{deployment}")

        page.locator('.ir-attention [data-action="run-stage"]').click()
        assert page.locator('.swal2-title').inner_text() == 'Run START?'
        page.locator('.swal2-confirm').click()

        page.wait_for_selector('.swal2-toast')
        assert page.locator('.swal2-toast .swal2-title').inner_text() == 'START started'
        assert page.locator('.swal2-popup:not(.swal2-toast)').count() == 0
        assert len(watch.posts('/api/run_stage/')) == 1

        assert boss.wait_for_stage(deployment, 'START')['status'] == 'finished'
        # The status changes on the page without loading it again (docs/features/web-ui-live-updates.md)
        start_id = boss.get_stages(deployment)['START']['id']
        wait_until(page, f"document.querySelector('.ir-flow-node[data-stage-id=\"{start_id}\"]').dataset.state === 'finished'", timeout=20000)
        watch.assert_clean()
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_log_dialog_keeps_the_steps(server, browser_context, boss, failed):

    page, watch = open_page(browser_context, server, f"/show_details/{failed}")

    quick = page.locator('.ir-step', has_text='quick').first
    quick.locator('[data-action="toggle-step"]').click()
    assert quick.locator('.ir-step-detail').is_visible()

    quick.locator('[data-action="show-log"]').click()
    page.wait_for_selector('#log-dialog.show')
    assert 'quick' in page.locator('#log-text').inner_text()
    assert page.locator('#log-dialog-title').inner_text().startswith('quick · ')

    # Errors of the failed step in the same dialog: the tab Errors
    page.locator('#log-dialog .btn-close').click()
    page.wait_for_selector('#log-dialog', state='hidden')
    page.locator('.ir-step[data-status="failed"] [data-log-type="errors"]').first.click()
    page.wait_for_selector('#log-dialog.show')
    assert 'No such file' in page.locator('#log-text').inner_text() or 'cannot access' in page.locator('#log-text').inner_text()
    assert page.locator('[data-action="log-tab"][data-log-type="errors"]').get_attribute('aria-selected') == 'true'
    page.locator('#log-dialog .btn-close').click()
    page.wait_for_selector('#log-dialog', state='hidden')

    # The steps are as before
    assert quick.locator('.ir-step-detail').is_visible()
    assert page.locator('.ir-step[data-status="failed"] .ir-step-detail').is_visible()
    assert steps_open(page)

    watch.assert_clean()



def test_cancel_a_deployment(server, browser_context, boss):

    deployment = fresh(boss, 'seq_wf')
    page, watch = open_page(browser_context, server, f"/show_details/{deployment}")

    # Canceling the dialog shows nothing
    page.locator('[data-action="cancel-deployment"]').click()
    assert page.locator('.swal2-confirm').inner_text() == 'Cancel deployment'
    page.locator('.swal2-cancel').click()
    page.wait_for_timeout(500)
    assert not page.locator('.swal2-popup').is_visible()
    assert watch.posts('/api/cancel_deployment/') == []

    page.locator('[data-action="cancel-deployment"]').click()
    page.locator('.swal2-confirm').click()
    page.wait_for_selector('.swal2-toast')
    assert page.locator('.swal2-toast .swal2-title').inner_text() == 'Deployment canceled'
    assert boss.get_deployment(deployment)['general']['status'] == 'canceled'
    # The header without the button, without loading the page again
    page.wait_for_selector('[data-action="cancel-deployment"]', state='detached', timeout=20000)
    assert 'canceled' in page.title()

    watch.assert_clean()



def test_edit_custom_data(server, browser_context, boss):

    deployment = fresh(boss, 'seq_wf')
    try:
        page, watch = open_page(browser_context, server, f"/show_details/{deployment}")

        page.locator('[data-action="edit-custom-data"]').click()
        page.locator('.swal2-html-container input').fill('T-<2>')
        page.locator('.swal2-confirm').click()
        page.wait_for_selector('.swal2-toast')
        assert page.locator('.swal2-toast .swal2-title').inner_text() == 'Custom data saved'

        assert boss.get_deployment(deployment)['custom_data']['ticket'] == 'T-<2>'
        wait_until(page, "document.querySelector('details.ir-custom-data').textContent.includes('T-<2>')", timeout=20000)
        page.locator('details.ir-custom-data > summary').click()
        assert 'T-<2>' in page.locator('details.ir-custom-data').inner_text()

        watch.assert_clean()
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_buttons_without_permission_do_nothing(server, browser_context, boss):

    deployment = fresh(boss, 'seq_wf')
    try:
        page, watch = open_page(browser_context, server, f"/show_details/{deployment}", user='intern')

        button = page.locator('.ir-attention [data-action="run-stage"]')
        assert button.get_attribute('aria-disabled') == 'true'
        assert button.get_attribute('title') == "Needs the permission 'run' for stage START"
        # Playwright waits for an enabled element: the click is sent anyway, as by a user
        button.click(force=True)
        page.locator('[data-action="cancel-deployment"]').click(force=True)
        page.wait_for_timeout(500)
        assert not page.locator('.swal2-popup').is_visible()
        assert watch.posts('/api/') == []

        watch.assert_clean()
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")
