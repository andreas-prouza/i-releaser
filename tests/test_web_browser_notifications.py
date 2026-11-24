"""Test message of a notification channel on the settings page, in a real browser (docs/features/notifications.md)

Skipped if Playwright or its Chromium is not installed, see tests/browser_tools.py.
"""
import pytest

from browser_tools import open_page
from notification_tools import SMTP_Server, Webhook_Server, wait_for
from web_server import WORKFLOWS, Web_Server
from test_notifications import TEAM, write_config


pytestmark = pytest.mark.browser


@pytest.fixture(scope='module')
def mail_server():
    s = SMTP_Server()
    yield s
    s.close()


@pytest.fixture(scope='module')
def hook_server():
    s = Webhook_Server()
    yield s
    s.close()


@pytest.fixture(scope='module')
def server(browser, mail_server, hook_server):
    s = Web_Server(workflows=WORKFLOWS, users=TEAM)
    write_config(s, {'channels': {'mail': mail_server.channel(), 'teams': hook_server.channel('teams')}})
    s.start()
    yield s
    s.close()



def test_send_a_test_mail(server, browser_context, mail_server):

    page, watch = open_page(browser_context, server, '/settings')

    page.locator('[data-action="test-notification"][data-channel="mail"]').click()

    # The own address, it can be changed
    field = page.locator('#notification-test-recipient')
    assert field.input_value() == 'boss@example.com'
    field.fill('ops@example.com')
    page.locator('.swal2-confirm').click()

    page.wait_for_selector('.swal2-toast')
    assert page.locator('.swal2-toast .swal2-title').inner_text() == 'Test message sent to ops@example.com'
    assert wait_for(lambda: mail_server.messages, 1)[0]['recipients'] == ['ops@example.com']
    watch.assert_clean()



def test_send_a_test_to_a_webhook(server, browser_context, hook_server):

    page, watch = open_page(browser_context, server, '/settings')

    page.locator('[data-action="test-notification"][data-channel="teams"]').click()
    assert page.locator('#notification-test-recipient').count() == 0
    page.locator('.swal2-confirm').click()

    page.wait_for_selector('.swal2-toast')
    assert page.locator('.swal2-toast .swal2-title').inner_text() == 'Test message sent to 127.0.0.1'
    assert wait_for(lambda: hook_server.requests, 1)[0]['body']['type'] == 'message'
    watch.assert_clean()
