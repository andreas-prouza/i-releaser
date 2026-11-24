"""The audit page in a real browser (docs/features/audit-log.md)

Skipped if Playwright or its Chromium is not installed, see tests/browser_tools.py.
"""
import pytest

from browser_tools import open_page, wait_until
from web_server import Web_Server


pytestmark = pytest.mark.browser


@pytest.fixture(scope='module')
def server(browser):
    s = Web_Server().start()
    yield s
    s.close()



def test_table_with_filter(server, browser_context):

    server.client('boss').create_deployment('seq_wf')

    page, watch = open_page(browser_context, server, '/settings/audit')

    wait_until(page, "document.querySelectorAll('#audit tbody tr').length > 0")
    events = page.locator('#audit tbody tr td:nth-child(3)').all_inner_texts()
    assert 'login' in events and 'deployment: create_workflow' in events

    # Filter by the event
    page.locator('.bootstrap-table-filter-control-event').select_option('login')
    wait_until(page, "[...document.querySelectorAll('#audit tbody tr td:nth-child(3)')].every(td => td.textContent === 'login')")

    assert page.locator('a[href="/settings/audit.csv"]').count() == 1
    assert page.locator('.ir-settings-tabs a[aria-current="page"]').inner_text() == 'Audit'
    watch.assert_clean()
