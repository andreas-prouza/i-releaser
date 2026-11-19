# Browser tests for the web app

- **Status:** ready (implemented on 2026-11-19 and tested locally; only the run on GitHub is missing: configured, not run yet)
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

- [x] `.venv/bin/pytest -m browser` runs the browser tests; `.venv/bin/pytest` without Playwright, or without its Chromium, skips them with the reason and passes (checked with a Playwright that can't be imported and with an empty `PLAYWRIGHT_BROWSERS_PATH`).
- [x] The smoke test fails for each of today's defects when it's run against today's pages (shown once, the result in this file): the script error of a stage `A->B`, the request to `unpkg.com`.
  Run on 2026-11-19 against commit `f3995bc` (before the fixes): `test_pages_have_no_errors` failed for both users with `request to another server: https://unpkg.com/bootstrap-table@1.22.1/...` (and `cdn.jsdelivr.net`), `test_stage_names_dont_break_the_deployment_page` with `typeof run_stage == 'undefined'`.
- [ ] GitHub runs the browser tests for every push and pull request. Configured in `.github/workflows/tests.yml` (`python -m playwright install --with-deps chromium`), not run yet.
- [x] Docs: [technik.md](../technik.md#entwicklung) (how to run them, package review), `CLAUDE.md` (commands).
- [x] Requirement 6: `tests/screenshots.py` makes the 10 pictures of `README.md` in about 10 seconds (`test_screenshots_script` checks that each picture of `README.md` is made). `docs/img/` is not replaced yet: the redesign will change the pictures again.


## Non-goals

* Tests in Firefox or Safari
* Comparing screenshots automatically
* Unit tests of single JavaScript functions (would need Node and a test runner)
* Browser tests on IBM i


## Decisions

* Playwright as development package: **yes** (2026-11-19).
* Screenshots of the documentation by script (requirement 6): **yes** (2026-11-19).
* The browser tests run with every `.venv/bin/pytest` if Playwright and its Chromium are installed, and are skipped otherwise (2026-11-19).
* The fixtures are in `tests/browser_tools.py` (not `conftest.py`): a test module imports them, so the other tests don't load Playwright. `Page_Watch` collects the failures of requirement 4; CSP violations are errors in the console.
* `playwright==1.65.2` is pinned: the version decides the build of Chromium.
* First tests (`tests/test_web_browser.py`, 12 tests, about 30 seconds): smoke test of every page for `boss` (admin) and `intern` (read); stage names `A->B`, `It's <b>x</b>`, `QA?`; values which would run as script in the steps, their log, the processing history and the object history; `None ready` for filtered objects in one request; switches of objects with `'` and `"`; no horizontal scrolling at 1440 and 1024 px; closing a log of the deployment history; token dialogs; permissions with special characters in names, and the error message when saving fails.
* Found by them: since SweetAlert2 11.26 ([static assets](web-ui-static-assets.md)) a dialog which is replaced by another one is resolved as dismissed. The steps window forgot its stage when a log opened over it, and didn't open again after the log. Fixed in `show_stage_steps`.


## Open questions

None.
