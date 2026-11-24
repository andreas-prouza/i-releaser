"""Two-factor authentication in a real browser (docs/features/two-factor-authentication.md, acceptance criteria)

Skipped if Playwright or its Chromium is not installed, see tests/browser_tools.py.
"""
import pytest

from browser_tools import open_page, wait_until
from web_server import Web_Server

from modules import totp


pytestmark = pytest.mark.browser


@pytest.fixture(scope='module')
def server(browser):
    """Started after `browser`: without Playwright the module is skipped before the web app is started"""
    s = Web_Server().start()
    yield s
    s.close()



def test_set_up_and_log_in_with_a_code(server, browser_context):

    page, watch = open_page(browser_context, server, '/user', user='runner')

    page.locator('[data-action="mfa-setup"]').click()
    page.wait_for_selector('.swal2-popup img.ir-qr-code')
    assert page.locator('.swal2-popup img.ir-qr-code').get_attribute('src').startswith('data:image/svg+xml;base64,')

    secret = page.locator('.swal2-popup .ir-code code').inner_text()
    step = totp.get_step()

    # A wrong code: the dialog stays and tells why
    page.locator('.swal2-input').fill('000000')
    page.locator('.swal2-confirm').click()
    page.wait_for_selector('.swal2-validation-message', state='visible')

    page.locator('.swal2-input').fill(totp.get_code(secret, step))
    page.locator('.swal2-confirm').click()

    # The recovery codes, shown once
    wait_until(page, "Swal.getTitle() && Swal.getTitle().textContent === 'Recovery codes'")
    codes = page.locator('.swal2-popup .ir-code code').inner_text().split('\n')
    assert len(codes) == 10
    page.locator('.swal2-confirm').click()

    page.wait_for_selector('[data-action="mfa-disable"]')
    # The wrong code
    watch.assert_clean(allow=('/api/mfa/enable',))

    # The login page with the code
    login = browser_context.new_page()
    login.context.clear_cookies()
    login.goto(f"http://127.0.0.1:{server.port}/workflows")
    login.locator('#login-user').fill('runner')
    login.locator('#login-password').fill('x')
    login.locator('#login-code').fill(totp.get_code(secret, step + 1))
    login.locator('button[type=submit]').click()
    login.wait_for_url('**/workflows')

    # A recovery code once
    login.context.clear_cookies()
    login.goto(f"http://127.0.0.1:{server.port}/workflows")
    login.locator('#login-user').fill('runner')
    login.locator('#login-password').fill('x')
    login.locator('#login-code').fill(codes[0])
    login.locator('button[type=submit]').click()
    login.wait_for_url('**/workflows')



def test_step_up_dialog_before_a_new_token(server, browser_context):

    client = server.client('intern')
    status, setup = client.post_json('/api/mfa/setup')
    _, enabled = client.post_json('/api/mfa/enable', {'code': totp.get_code(setup['secret'], totp.get_step())})

    # The code of the login is older than C_2FA_STEP_UP_MINUTES
    page, watch = open_page(browser_context, server, '/user', user=None)
    page.context.add_cookies([{'name': 'session_id', 'value': client.session_id, 'url': f"http://127.0.0.1:{server.port}"}])
    expire_code(server, client)
    page.goto(f"http://127.0.0.1:{server.port}/user", wait_until='networkidle')

    page.locator('[data-action="new-token"]').click()
    page.locator('.swal2-confirm').click()

    # The dialog asks for the code and creates the token afterwards
    wait_until(page, "Swal.getTitle() && Swal.getTitle().textContent === 'Confirm with your authenticator app'")
    page.locator('.swal2-input').fill(enabled['recovery_codes'][0])
    page.locator('.swal2-confirm').click()

    wait_until(page, "Swal.getTitle() && Swal.getTitle().textContent === 'Token OBI extension created'")
    # The first request, which asks for the code
    watch.assert_clean(allow=('/api/v2/tokens',))



def expire_code(server, client) -> None:

    import json, os, time

    path = os.path.join(server.web_dir, 'sessions', f"{client.session_id}.json")
    with open(path) as f:
        data = json.load(f)
    data['session-data']['mfa_at'] = time.time() - 3600
    with open(path, 'w') as f:
        json.dump(data, f)
