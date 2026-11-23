"""Scheduled run of a stage in a real browser (docs/features/scheduled-stage-run.md): Run at…, the time zone of the browser, Cancel schedule

Skipped if Playwright or its Chromium is not installed, see tests/browser_tools.py.
"""
import datetime

import pytest

from browser_tools import VIEWPORT, open_page, wait_until
from web_server import Web_Server


pytestmark = pytest.mark.browser

TOKYO = datetime.timezone(datetime.timedelta(hours=9))


@pytest.fixture(scope='module')
def server(browser):
    """Started after `browser`: without Playwright the module is skipped before the web app is started"""
    # Mode service, but no service: the scheduled run stays in the queue
    s = Web_Server(settings="C_PROCESSING_MODE = 'service'\n").start()
    yield s
    s.close()


@pytest.fixture()
def boss(server):
    return server.client('boss')


@pytest.fixture()
def tokyo_context(browser):
    """A user whose browser is in another time zone than the server"""
    context = browser.new_context(viewport=VIEWPORT, timezone_id='Asia/Tokyo', locale='en-US')
    yield context
    context.close()


def fresh(boss) -> int:
    from test_web_deployment import cancel_open_deployments
    cancel_open_deployments(boss, 'seq')
    return boss.create_deployment('seq_wf')


def attention_text(page) -> str:
    return page.locator('.ir-attention-text').inner_text()



def test_schedule_and_cancel_in_the_time_zone_of_the_browser(server, tokyo_context, boss):

    deployment = fresh(boss)
    start_id = boss.get_stages(deployment)['START']['id']
    # 10:00 in Tokyo, the day after tomorrow: 01:00 UTC
    day = (datetime.datetime.now(TOKYO) + datetime.timedelta(days=2)).date()

    try:
        page, watch = open_page(tokyo_context, server, f"/show_details/{deployment}")

        page.locator('.ir-attention [data-action="schedule-stage"]').click()
        assert page.locator('.swal2-title').inner_text() == 'Run START at …'
        assert 'Time zone of your browser: GMT+9' in page.locator('.swal2-html-container').inner_text()

        page.locator('#schedule-run-at').fill(f"{day.isoformat()}T10:00")
        page.locator('#schedule-run_all').check()
        page.locator('.swal2-confirm').click()

        page.wait_for_selector('.swal2-toast')
        toast = page.locator('.swal2-toast .swal2-title').inner_text()
        assert toast.startswith(f"START is scheduled for {day.isoformat()} 10:00 GMT+9."), toast
        assert 'The processing service is not running' in toast
        assert len(watch.posts('/api/run_stage/')) == 1

        [job] = boss.get_deployment(deployment)['processing_jobs']
        assert job['run_at'] == f"{day.isoformat()}T01:00:00+00:00"
        assert job['continue_run'] is False

        # Shown in the time zone of the browser, without loading the page again
        wait_until(page, f"document.querySelector('.ir-flow-node[data-stage-id=\"{start_id}\"]').dataset.state === 'scheduled'", timeout=20000)
        wait_until(page, "document.querySelector('.ir-attention time') !== null", timeout=20000)
        assert attention_text(page) == f"Stage START runs at {day.isoformat()} 10:00 GMT+9, scheduled by BOSS. The processing service is not running."
        assert page.locator('.ir-attention time').get_attribute('title') == job['run_at']

        # The steps panel after a reload: also in the time zone of the browser
        page.reload(wait_until='networkidle')
        page.locator('[data-action="toggle-steps"]').click()
        assert page.locator('.ir-steps-schedule').inner_text().strip() == f"Runs at {day.isoformat()} 10:00 GMT+9 (all steps), scheduled by BOSS"

        page.locator('.ir-attention [data-action="cancel-schedule"]').click()
        assert page.locator('.swal2-title').inner_text() == 'Cancel the scheduled run of START?'
        page.locator('.swal2-confirm').click()

        page.wait_for_selector('.swal2-toast')
        assert page.locator('.swal2-toast .swal2-title').inner_text() == 'Scheduled run of START canceled'
        wait_until(page, "document.querySelector('.ir-attention').classList.contains('k-ready')", timeout=20000)
        assert boss.get_deployment(deployment)['processing_jobs'] == []
        assert boss.get_stages(deployment)['START']['status'] == 'ready'

        watch.assert_clean()
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_time_in_the_past_is_shown_in_the_dialog(server, browser_context, boss):

    deployment = fresh(boss)
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')

    try:
        page, watch = open_page(browser_context, server, f"/show_details/{deployment}")

        page.locator('.ir-attention [data-action="schedule-stage"]').click()
        page.locator('#schedule-run-at').fill(yesterday)
        page.locator('.swal2-confirm').click()

        page.wait_for_selector('.swal2-validation-message')
        assert 'in the past' in page.locator('.swal2-validation-message').inner_text()
        # The dialog stays open, nothing is queued
        assert page.locator('.swal2-popup').is_visible()
        assert boss.get_deployment(deployment)['processing_jobs'] == []

        page.locator('.swal2-cancel').click()
        # The answer 422 of the server is expected here
        watch.assert_clean(allow=('422',))
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")
