"""Four-eyes check in a real browser (docs/features/four-eyes-check.md)

Skipped if Playwright or its Chromium is not installed, see tests/browser_tools.py.
"""
import pytest

from browser_tools import open_page, wait_until
from web_server import WORKFLOWS, Web_Server
from test_four_eyes_check import EYES_WF, TEAM


pytestmark = pytest.mark.browser


@pytest.fixture(scope='module')
def server(browser):
    s = Web_Server(workflows={**WORKFLOWS, 'eyes_wf': EYES_WF}, users=TEAM).start()
    yield s
    s.close()



def test_approve_on_the_deployment_page(server, browser_context):

    creator = server.client('creator')
    deployment = creator.create_deployment('eyes_wf')
    creator.run_stage(deployment, 'START')
    creator.wait_for_stage(deployment, 'START')

    page, watch = open_page(browser_context, server, f"/show_details/{deployment}", user='checker')

    page.locator('.ir-attention [data-action="approve-stage"]').click()
    page.locator('.swal2-confirm').click()

    # The page updates itself: the stage is approved and ready to run
    wait_until(page, "document.querySelector('.ir-attention') && document.querySelector('.ir-attention').textContent.includes('Approved by checker')")
    watch.assert_clean()
