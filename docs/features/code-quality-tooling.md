# Code quality: linter, tests, dependencies

- **Status:** ready (partly implemented 2026-11-24, see [progress](#progress))
- **Type:** improvement
- **Priority:** P2
- **Source:** Code review 2026-11-23


## Current situation

**Static checks:** none. No linter, formatter or type checker; CI runs `pytest` and `pip-audit` only ([tests.yml](../../.github/workflows/tests.yml)).
Indentation is mixed (2 spaces in `stages.py`, `deploy_action.py`; 4 in `modules/db/`; methods at 4 and bodies at 6 in `meta_file.py`). About 65 % of the functions of `modules/` have type hints for the result.
Errors a linter finds at once were found by hand in this review: unused imports, shadowed built-ins (`dict`, `type`, `id`), a name `do` which hides the module `do` ([meta_file.py:1233](../../modules/meta_file.py#L1233)), `logging.exception` outside of `except`, mutable default arguments.

**Tests** (555 tests, very good coverage of the behaviour):

* The same database setup (patch `get_db_connection.__defaults__`, `C_META_DIR`, `create_tables`) is copied into 9 files (e.g. [test_stage_flow.py](../../tests/test_stage_flow.py), [test_commands.py](../../tests/test_commands.py)), with `setUp`/`tearDown` instead of `addCleanup`: an error in `tearDown` leaves the next tests on the wrong database.
* 44 web servers are started (copy of the repository + uvicorn each); `test_service_auto_start.py` starts one per test.
* Fixed `sleep` before checks (e.g. `test_web_deployment.py`, `test_service_auto_start.py`): slow, and flaky on a busy CI.
* The `browser` fixture skips on every error of Chromium, so a broken installation in CI silently skips all browser tests.
* No coverage measurement; the web app runs in a subprocess, so coverage would need `COVERAGE_PROCESS_START`.
* No test imports the modules in a new interpreter (the [circular import](../bugfixes/minor-code-defects-2026-11.md) wasn't noticed).

**Dependencies:** `pyodbc`, `requests`, `python-multipart`, `itsdangerous`, `watchdog`, `jinja2` aren't pinned ([requirements.txt](../../requirements.txt)); no lock file. The venv on IBM i is created with `--system-site-packages`, so it can use other versions than CI.


## Requirements

1. **ruff** for lint and format (configuration in `pyproject.toml`): rules `E`, `F`, `W`, `B` (bugbear), `UP`, `I` (imports); indentation unified to 4 spaces in one commit (listed in `.git-blame-ignore-revs`). CI fails on lint errors. Needs the [package review](../technik.md#package-prüfung) (astral-sh/ruff, far above 200 stars).
2. **Tests:**
   * one fixture `temp_db` in `conftest.py` for all database tests (with `addCleanup`/`yield`);
   * one module-scoped web server where tests don't need their own; `wait_until` instead of fixed `sleep`;
   * in CI (`CI=true`) the `browser` fixture fails instead of skipping when Chromium can't start;
   * a test which imports every module of `modules/` and `webapp/web_modules/` in a new interpreter;
   * `pytest-timeout` (development package, review) with 120 seconds per test.
3. **Coverage** with `coverage` (development package, review), also for the web app in the subprocess; report in CI, no minimum at first.
4. **Dependencies:** every package of `requirements.txt` pinned (`==`); `requirements-dev.txt` too. A `constraints.txt` with the versions tested in CI; `setup3.13.sh` installs with it. Unused packages removed (see [minor code defects](../bugfixes/minor-code-defects-2026-11.md)).
5. **Type hints:** new code (the [core redesign](core-redesign.md)) has them completely; a type checker (mypy or pyright) for `modules/domain/` and `modules/application/` only, later more.
6. `CLAUDE.md`: remove the header of another project ("Guide for working on **Profito**"); add the lint command.


## Acceptance criteria

- [ ] `ruff check` and `ruff format --check` pass in CI.
- [x] The test run is at least 30 % faster than before, with the same number of tests: 1004 tests in 101 to 114 seconds instead of 445 (measured locally with 12 CPUs and with 4 workers, 2026-11-24; in CI not yet measured).
- [x] No fixed `sleep` in the tests except where a time has to pass (documented in the test): the waits for something to happen use `wait_until` (or `wait_for_stage`, a marker file of a slow request, the log of the fake ODBC driver); what is left are polls in loops, work simulated by test scripts, and waits with the comment "A time has to pass" (2026-11-24).
- [ ] `pip install -r requirements.txt` gives the same versions on IBM i and in CI.


## Non-goals

* A minimum coverage which makes CI fail.
* Type checking of the whole code base.


## Progress

| Requirement | Status |
|---|---|
| 1 ruff | partly: `pyproject.toml` with the rules `F` (undefined and unused names), `E9` (syntax) and `B` (bugbear), a job `lint` in CI. The 61 findings of `F` are fixed (unused imports; a duplicated test helper, unused variables, a loop variable which hid the module `do`). The 47 findings of `B` (2026-11-24): mutable default arguments replaced by `None`, `zip(..., strict=True)` where both sides must have the same length (rows of the DB deployment), `raise ... from`, and ten tests which accepted any exception now expect the right one: the workflow validation raises `workflow.Invalid_Workflow_Error` (also for an invalid stage, with the file name), a missing job `errors.Not_Found_Error`. `Body`/`Query`/`Depends` of FastAPI are allowed in defaults. The style rules (`E`, `W`, `UP`, `I`) and the indentation follow, see decisions |
| 2 Tests | partly: the tests run in parallel (`pytest-xdist`, `pytest.ini`), 101 instead of 445 seconds; the import test exists (every module first in its own interpreter, `tests/test_review_2026_11_modules.py`); the browser tests fail in CI (`CI=true`) instead of being skipped; `pytest-timeout` with 120 seconds per test (`pytest.ini`); one database setup for the tests in the test process (`tests/db_tools.py`: `use_temp_db(self)` for unittest classes, the fixture `temp_db` of `conftest.py`), with `addCleanup` instead of 9 copies with `tearDown`; `wait_until` of `tests/web_server.py` instead of fixed `sleep` (the remaining ones: a time has to pass, with a comment). Not done: one module-scoped web server where tests don't need their own (with the parallel run the time of a file counts less) |
| 3 Coverage | configured: `coverage` in `requirements-dev.txt` and `pyproject.toml`, also for the web app in its process (a `.pth` file in CI); report in CI. Not run on GitHub yet |
| 4 Dependencies | finished: every package of `requirements.txt` pinned except `pyodbc` (from the IBM i open source packages), `requirements-dev.txt` pinned; `itsdangerous` and `jsonschema` removed from the runtime |
| 5 Type hints | open (with the [core redesign](core-redesign.md)) |
| 6 CLAUDE.md | finished |


## Decisions (2026-11-24)

* Package review (2026-11-24, all MIT/Apache, active): `ruff` 51,400 stars / 2,775 forks; `pytest-timeout` 264 / 82; `coverage` 3,433 / 567 (`coveragepy/coveragepy`). All only in `requirements-dev.txt`.
* `ruff --fix` removes imports which are only there for their side effect: `from etc import logger_config` (configures the log) and `from index import app` in `webapp/wsgi.py` were restored with `# noqa: F401`. Such an import always gets the comment.
* The indentation is unified in its own commit, after the changes of the review are committed: in the same diff it would hide them. Then the rules `E`, `W`, `B`, `UP`, `I` follow.
* `pyodbc` isn't pinned: on IBM i it comes from the open source packages of IBM (the venv uses `--system-site-packages`), pip would try to build another version.
* Faster tests (2026-11-24): the slowest tests wait for real things (the watchdog of the processing service, runs of stages, pages in the browser); removing fixed `sleep` saves seconds, not minutes. Parallel processes save 75 %: `pytest-xdist` (review: 1934 stars, 307 forks, MIT), `--dist loadfile` keeps the tests of a file together (their module fixtures, e.g. a web server, are shared). Each web server of the tests has its own directory and port, the tests in the test process their own database (`tests/db_tools.py`): they don't share anything between processes. Three full runs with 4, 6 and 12 workers passed.
* `B` (bugbear) is independent of the indentation and finds defects, so it came before the other rules.


## Open questions (answered 2026-11-24)

* Indentation: unify to 4 spaces (one large commit, `git blame` with ignore file) or keep 2 spaces where it is? Proposal: 4 spaces, as most of `modules/db/` and the tests.
* Pinning `pyodbc` on IBM i: it comes from the IBM i open source packages (yum, `--system-site-packages`). Pin only in CI?
