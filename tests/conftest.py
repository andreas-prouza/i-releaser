import os, sys

# The repository root, so `etc` and `modules` are found
ROOT_DIR = os.path.realpath(f"{os.path.dirname(__file__)}/..")
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.dirname(__file__))


import pytest


@pytest.fixture(autouse=True)
def no_local_app_settings(tmp_path, monkeypatch):
    """Tests never use the etc/app.json of the installation"""
    from etc import constants
    monkeypatch.setattr(constants, 'C_APP_SETTINGS_FILE', str(tmp_path / 'app.json'))
