"""The lists in a real browser (docs/features/web-ui-lists.md, acceptance criteria "Browser tests")

Skipped if Playwright or its Chromium is not installed, see tests/browser_tools.py.
"""
import pytest

from browser_tools import open_page, wait_until
from test_lists import LIST_WORKFLOWS, insert_objects
from web_server import Web_Server


pytestmark = pytest.mark.browser


@pytest.fixture(scope='module')
def server(browser):
    """Started after `browser`: without Playwright the module is skipped before the web app is started"""
    s = Web_Server(workflows=LIST_WORKFLOWS).start()
    yield s
    s.close()


@pytest.fixture()
def boss(server):
    return server.client('boss')


def versions(page) -> list[str]:
    return page.locator('#deployments tbody tr td:first-child').all_inner_texts()



def test_filter_sort_and_open_deployments(server, browser_context, boss):

    deployments = [boss.create_deployment('fields_wf') for _ in range(3)]
    boss.post(f"/api/cancel_deployment/{deployments[0]}")
    try:
        page, watch = open_page(browser_context, server, '/project/fields')

        # Newest first
        assert versions(page) == ['Version 3', 'Version 2', 'Version 1']

        page.locator('#deployments th[data-field="version"] .sortable').click()
        assert versions(page) == ['Version 1', 'Version 2', 'Version 3']

        # Open ones only
        page.locator('label[for="which-open"]').click()
        assert versions(page) == ['Version 2', 'Version 3']
        page.locator('label[for="which-all"]').click()

        page.select_option('.bootstrap-table-filter-control-status', 'canceled')
        wait_until(page, "$('#deployments').bootstrapTable('getData').length === 1")
        assert versions(page) == ['Version 1']

        # A click on the row (not on the link) opens the deployment
        with page.expect_navigation():
            page.locator('#deployments tbody tr td:nth-child(3)').first.click()
        assert page.url.endswith(f"/show_details/{deployments[0]}")

        watch.assert_clean()
    finally:
        for deployment in deployments:
            boss.post(f"/api/cancel_deployment/{deployment}")



def test_page_through_and_search_objects(server, browser_context, boss):

    deployment = boss.create_deployment('seq_wf')
    insert_objects(server, deployment, [('prodlib', f"item{i:03}", 'pgm') for i in range(60)])
    try:
        page, watch = open_page(browser_context, server, '/list-objects')

        assert page.locator('#objects tbody tr').count() == 25
        assert 'of 60 rows' in page.locator('.pagination-info').inner_text()

        page.locator('.page-link[aria-label="to page 3"]').click()
        wait_until(page, "document.querySelectorAll('#objects tbody tr').length === 10")

        page.locator('.bootstrap-table .search input').press_sequentially('item05')
        wait_until(page, "document.querySelector('.pagination-info').textContent.includes('of 10 rows')", timeout=10000)
        assert all(name.startswith('item05') for name in page.locator('#objects tbody tr td:nth-child(3)').all_inner_texts())

        page.locator('#objects tbody [data-action="object-history"]').first.click()
        page.wait_for_selector('#object-history.show')
        assert page.locator('#object-history-body a').first.get_attribute('href') == f"/show_details/{deployment}"

        watch.assert_clean()
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_start_a_workflow_with_its_fields(server, browser_context, boss):

    page, watch = open_page(browser_context, server, '/project/fields')

    page.locator('[data-action="start-workflow"]').first.click()
    assert page.locator('.swal2-title').inner_text() == 'Start a workflow'
    page.locator('#start-workflow-name').select_option('fields_wf')
    page.locator('.swal2-html-container label', has_text='jira.issue').wait_for()
    page.locator('#start-field-0').fill('T-<9>')
    page.locator('#start-field-1').fill('ERP-1')

    with page.expect_navigation():
        page.locator('.swal2-confirm').click()

    deployment = int(page.url.rstrip('/').split('/')[-1])
    try:
        assert boss.get_deployment(deployment)['custom_data'] == {'ticket': 'T-<9>', 'jira': {'issue': 'ERP-1'}}
        watch.assert_clean()
    finally:
        boss.post(f"/api/cancel_deployment/{deployment}")
