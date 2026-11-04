# Tests in the repository

- **Status:** ready (Implemented. Open: the first run on GitHub.)
- **Type:** improvement
- **Priority:** P1


## Current situation

* The unit tests are not part of this repository. They are in a separate repository next to it (`../unit-tests/`, `unittest`).
* Several of them are outdated since the switch to SQLite (e.g. `Meta_File(file_name=...)`) and fail.
* `CLAUDE.md` names `pytest`, `requirements-dev.txt` and `pip-audit`, which don't exist yet.
* `CLAUDE.md` says a feature is only done when its acceptance criteria are covered by tests.
* No automatic test run (CI).
* `docs/open-topics.md`: "Create tests".


## Requirements

1. Tests are in the repository (e.g. `tests/`).
2. Test runner as named in `CLAUDE.md` (`pytest`; it also runs existing `unittest` tests). `requirements-dev.txt` contains the test tools and `pip-audit`.
3. Outdated tests are fixed or removed. All tests pass.
4. Tests don't need an IBM i: commands are recorded or faked (like `Fake_Db` and `Sim_Db` of the DB deployment tests). Tests which need an IBM i are marked and skipped by default.
5. Tests never use the real `var/`, `etc/` or `meta/` of the installation (temporary directories).
6. A helper starts the web app for tests in a temporary directory (with `I_RELEASER_LOCAL_DEBUGGING`).
7. Each bugfix in `docs/bugfixes/` gets a regression test.
8. CI runs the tests and `pip-audit` for every push and pull request.


## Acceptance criteria

- [x] `.venv/bin/pytest` runs all tests of the repository and they pass.
- [ ] CI runs on push and pull request and shows the result.
- [ ] `pip-audit -r requirements.txt` runs in CI.
- [x] `CLAUDE.md` describes how to run the tests.


## Non-goals

* Tests of the user interface in a browser


## Decisions

* Move the tests of `../unit-tests/`? **New `tests/` folder. Copy the working ones (hooks, Jira, step overhead, processing service, reset stage, DB deployment), leave the outdated ones out.**
* CI on GitHub Actions? **Yes.**
