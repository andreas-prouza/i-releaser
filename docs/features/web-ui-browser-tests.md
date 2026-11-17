# Browser tests for the web app

- **Status:** draft
- **Type:** improvement
- **Priority:** P2
- **Source:** [Modernization of the web front end](web-ui-modernization.md)


## Current situation

* The tests in `tests/` call the web app with HTTP (`tests/web_server.py`, `Client`). They check status codes, JSON and HTML, but no test runs the JavaScript of a page.
* The web app has about 1,500 lines of JavaScript, and will keep a similar amount in files.
* All defects of the analysis of 2026-11-16 were only visible in a browser:
  [permissions page](../bugfixes/permissions-page-names-in-selectors.md), [stage names](../bugfixes/stage-name-breaks-deployment-page.md), [objects table](../bugfixes/deployment-objects-table.md), [values in handlers](../bugfixes/web-values-run-as-script.md).
  None of them fails a test of today.
* For the analysis the pages were opened with a headless Chrome driven by a hand-written script. That's not a base for tests.


## Requirements

1. Tests which open the web app of `tests/web_server.py` in a real browser (Chromium, headless), written with pytest like the other tests.
2. Package: **Playwright for Python** (`playwright`), only in `requirements-dev.txt`.
   * Criteria of [architektur.md](../architektur.md): `microsoft/playwright-python`, 15,115 stars, 1,258 forks, Apache-2.0 (2026-11-16). Result into the [package review](../technik.md#package-prüfung).
   * No `pytest-playwright`: one fixture in `tests/conftest.py` starts the browser.
   * The browser is installed once with `.venv/bin/playwright install chromium` (about 150 MB, outside the repository).
3. The tests are marked `@pytest.mark.browser`.
   * Without Playwright or its browser they are skipped, with the reason. So `.venv/bin/pytest` still works on IBM i and on a machine without it.
   * GitHub runs them (`.github/workflows/tests.yml`).
4. Every browser test fails on: an error in the console, an exception of the page, a request to another server, a failed request of a file, and a violation of the Content-Security-Policy.
5. First tests:
   * Smoke: every page opens without the failures of 4, for an administrator and for a user with `read` only.
   * The acceptance criteria marked `Browser test` in the bugfixes and in the steps of the [modernization](web-ui-modernization.md#steps), as these are done.
6. A script creates the screenshots of [README.md](../../README.md) from test data (`docs/img/`), so they can be renewed after a change of the layout.


## Acceptance criteria

- [ ] `.venv/bin/pytest -m browser` runs the browser tests; `.venv/bin/pytest` without Playwright skips them and passes.
- [ ] The smoke test fails for each of today's defects when it's run against today's pages (shown once, the result in this file): the script error of a stage `A->B`, the request to `unpkg.com`.
- [ ] GitHub runs the browser tests for every push and pull request.
- [ ] Docs: [technik.md](../technik.md#entwicklung) (how to run them, package review), `CLAUDE.md` (commands).


## Non-goals

* Tests in Firefox or Safari
* Comparing screenshots automatically
* Unit tests of single JavaScript functions (would need Node and a test runner)
* Browser tests on IBM i


## Open questions

1. Playwright as development package: **yes (recommended)**?
   * Without it, the criteria marked `Browser test` are manual checks, written down as a list in each step, and defects like those of 2026-11-16 can come back unnoticed.
   * Alternative Selenium (`SeleniumHQ/selenium`): also meets the criteria, but needs a separate driver for the browser and more code for waiting.
2. Should the browser tests run by default (`.venv/bin/pytest`) if Playwright is installed (**recommended**), or only with `-m browser`? They add about a minute.
3. Screenshots of the documentation by script (requirement 6): wanted?
