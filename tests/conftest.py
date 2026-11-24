import os, sys

# The repository root, so `etc` and `modules` are found
ROOT_DIR = os.path.realpath(f"{os.path.dirname(__file__)}/..")
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.dirname(__file__))


import pytest

# Fixtures of the browser tests, registered once: a session fixture imported into two test modules would start Playwright twice
from browser_tools import browser, browser_context  # noqa: F401


@pytest.fixture(autouse=True)
def no_local_app_settings(tmp_path, monkeypatch):
    """Tests never use the etc/app.json of the installation"""
    from etc import constants
    monkeypatch.setattr(constants, 'C_APP_SETTINGS_FILE', str(tmp_path / 'app.json'))


@pytest.fixture()
def temp_db(request) -> str:
    """A new database and meta directory for the test (tests/db_tools.py). Returns the directory."""
    import db_tools
    return db_tools.use_temp_db(db_tools.Cleanups(request))
