"""
Browser tests: the web app of tests/web_server.py in a real Chromium (Playwright, docs/features/web-ui-browser-tests.md).

The tests are skipped if Playwright or its Chromium is not installed:

    .venv/bin/pip install -r requirements-dev.txt
    .venv/bin/python -m playwright install chromium

The fixtures `browser` and `browser_context` are registered in conftest.py; import the helpers: `from browser_tools import Page_Watch, open_page`

The pages have a Content-Security-Policy without 'unsafe-eval': `page.wait_for_function` evaluates its expression with
eval and is blocked. Use `wait_until` (page.evaluate is not affected).
"""
import time

import os

import pytest


VIEWPORT = {'width': 1440, 'height': 900}



@pytest.fixture(scope='session')
def browser():

    # In CI the browser tests must run: a broken installation fails instead of skipping them (docs/features/code-quality-tooling.md)
    in_ci = os.environ.get('CI', '').lower() == 'true'

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        if in_ci:
            raise
        pytest.skip('Playwright is not installed (.venv/bin/pip install -r requirements-dev.txt)')

    playwright = sync_playwright().start()

    try:
        chromium = playwright.chromium.launch()
    except Exception as e:
        playwright.stop()
        if in_ci:
            raise
        pytest.skip(f"Chromium of Playwright is not installed (.venv/bin/python -m playwright install chromium): {str(e).splitlines()[0]}")

    yield chromium

    chromium.close()
    playwright.stop()



@pytest.fixture()
def browser_context(browser):
    context = browser.new_context(viewport=VIEWPORT)
    yield context
    context.close()



class Page_Watch:
    """Collects what must not happen on a page: script errors, errors in the console, requests to other servers,
    failed requests and responses with an error status.

    `allow`: substrings of messages which are expected (e.g. the 404 of an error page).
    """

    def __init__(self, page, origin: str):
        self.page = page
        self.origin = origin
        self.problems: list[str] = []
        self.console: list[str] = []
        self.requests: list[str] = []

        page.on('console', self._on_console)
        page.on('pageerror', lambda error: self.problems.append(f"script error: {error}"))
        page.on('request', self._on_request)
        page.on('requestfailed', self._on_request_failed)
        page.on('response', lambda response: response.status >= 400 and self.problems.append(f"HTTP {response.status}: {response.url}"))


    def _on_console(self, message) -> None:
        self.console.append(message.text)
        if message.type == 'error':
            # "Failed to load resource" doesn't name the resource in its text
            url = (message.location or {}).get('url', '')
            self.problems.append(f"console error: {message.text}{f' ({url})' if url else ''}")


    def _on_request_failed(self, request) -> None:
        # Leaving a page ends its live updates (/api/watch_state): that's not an error
        if request.resource_type == 'eventsource' and 'ERR_ABORTED' in (request.failure or ''):
            return
        self.problems.append(f"failed request: {request.url} ({request.failure})")


    def _on_request(self, request) -> None:
        self.requests.append(f"{request.method} {request.url}")
        if not request.url.startswith((self.origin + '/', 'data:', 'about:', 'blob:')):
            self.problems.append(f"request to another server: {request.url}")


    def posts(self, path: str) -> list[str]:
        return [r for r in self.requests if r.startswith('POST ') and path in r]


    def clear(self) -> None:
        self.problems.clear()
        self.console.clear()
        self.requests.clear()


    def assert_clean(self, allow: tuple = ()) -> None:
        problems = [p for p in self.problems if not any(a in p for a in allow)]
        assert problems == [], '\n'.join(problems)



def open_page(context, server, path: str, user: str|None='boss', wait: str='networkidle'):
    """Opens a page of the web app, logged in as `user` (the session of a test client)"""

    origin = f"http://127.0.0.1:{server.port}"

    if user is not None:
        context.add_cookies([{'name': 'session_id', 'value': server.client(user).session_id, 'url': origin}])

    page = context.new_page()
    watch = Page_Watch(page, origin)
    page.goto(origin + path, wait_until=wait)

    return page, watch



def horizontal_overflow(page) -> int:
    """Pixels the page is wider than the window"""
    return page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")



def wait_until(page, expression: str, timeout: float = 30000) -> None:
    """Waits until a JavaScript expression of the page is true. Like page.wait_for_function, which the
    Content-Security-Policy of the web app blocks (it uses eval). Errors while the page changes are tried again."""

    end = time.time() + timeout / 1000
    last_error = None

    while True:
        try:
            if page.evaluate(expression):
                return
        except Exception as e:
            last_error = e
        if time.time() > end:
            raise TimeoutError(f"Not true within {timeout} ms: {expression}" + (f" (last error: {last_error})" if last_error else ''))
        page.wait_for_timeout(100)
