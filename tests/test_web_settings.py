"""Settings changed in the web app, the module (docs/features/settings-in-web-app.md). The pages: test_settings_in_web_app.py"""
import json
import os
from unittest.mock import patch

import pytest

from etc import constants
from modules import errors, settings_check, web_settings


@pytest.fixture()
def app_file(tmp_path):
    """A new etc/app.json; the settings and the state of the module are set back after the test"""

    path = tmp_path / 'app.json'
    current = {name: getattr(constants, name) for name in web_settings.EDITABLE}
    with patch.object(constants, 'C_APP_SETTINGS_FILE', str(path)), patch.multiple(constants, **current), \
         patch.object(web_settings, '_applied', None):
        yield path


def stored(path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}



def test_change_is_stored_and_counts_at_once(app_file):

    old = web_settings.change('C_MAX_PARALLEL_STEPS', 7, 'boss')

    assert old == web_settings.get_base('C_MAX_PARALLEL_STEPS')
    assert stored(app_file) == {'C_MAX_PARALLEL_STEPS': 7}
    assert constants.C_MAX_PARALLEL_STEPS == 7
    assert web_settings.get_source('C_MAX_PARALLEL_STEPS') == web_settings.SOURCE_WEB_APP



def test_other_settings_of_the_file_stay(app_file):

    app_file.write_text(json.dumps({'C_PROCESSING_MODE': 'service', 'C_SERVICE_AUTO_START': True}))
    web_settings.change('C_RETENTION_ARCHIVE', True, 'boss')

    assert stored(app_file) == {'C_PROCESSING_MODE': 'service', 'C_SERVICE_AUTO_START': True, 'C_RETENTION_ARCHIVE': True}



@pytest.mark.parametrize('name, value', [('C_MAX_PARALLEL_STEPS', 0), ('C_MAX_PARALLEL_STEPS', 'four'), ('C_MAX_PARALLEL_STEPS', True),
                                         ('C_RETENTION_ARCHIVE', 1), ('C_GIT_BRANCH_PRODUCTION', 5), ('C_GIT_BRANCH_PRODUCTION', ''),
                                         ('C_SCHEDULE_MAX_DELAY_MINUTES', -1)])
def test_invalid_value_is_refused_and_nothing_is_stored(app_file, name, value):

    before = getattr(constants, name)
    with pytest.raises(errors.Invalid_Input_Error, match=name):
        web_settings.change(name, value, 'boss')

    assert not app_file.exists()
    assert getattr(constants, name) == before



@pytest.mark.parametrize('name', ['C_EXTERNAL_URL', 'C_2FA_POLICY', 'C_LOGIN_MAX_FAILURES', 'C_APP_DB_FILE', 'C_META_DIR', 'C_LOG_MAX_MB', 'C_UNKNOWN'])
def test_settings_of_the_file_can_not_be_changed(app_file, name):

    with pytest.raises(errors.Invalid_Input_Error, match='etc/settings.py'):
        web_settings.change(name, 1, 'boss')
    with pytest.raises(errors.Invalid_Input_Error, match='etc/settings.py'):
        web_settings.reset(name, 'boss')

    assert not app_file.exists()



def test_a_whole_number_sent_as_float_is_stored_as_number(app_file):
    """JavaScript sends 4 as 4; a client may send 4.0"""

    web_settings.change('C_SERVICE_MAX_PARALLEL_JOBS', 4.0, 'boss')
    assert stored(app_file) == {'C_SERVICE_MAX_PARALLEL_JOBS': 4}
    assert isinstance(constants.C_SERVICE_MAX_PARALLEL_JOBS, int)



def test_reset_uses_the_value_of_the_settings_file_or_the_default_again(app_file):

    web_settings.change('C_COMMAND_TIMEOUT_SECONDS', 30, 'boss')
    web_settings.change('C_HEALTH_MIN_FREE_MB', 10, 'boss')

    with patch.object(web_settings, 'get_file_settings', lambda: {'C_COMMAND_TIMEOUT_SECONDS': 600}):
        assert web_settings.reset('C_COMMAND_TIMEOUT_SECONDS', 'boss') == 30
        assert constants.C_COMMAND_TIMEOUT_SECONDS == 600
        assert web_settings.get_source('C_COMMAND_TIMEOUT_SECONDS') == web_settings.SOURCE_SETTINGS

    assert stored(app_file) == {'C_HEALTH_MIN_FREE_MB': 10}
    web_settings.reset('C_HEALTH_MIN_FREE_MB', 'boss')
    assert constants.C_HEALTH_MIN_FREE_MB == web_settings.get_defaults()['C_HEALTH_MIN_FREE_MB']



def test_refresh_takes_a_change_of_another_process(app_file):

    web_settings.refresh()
    # Written by another worker
    app_file.write_text(json.dumps({'C_RETENTION_DAYS': 90}))
    web_settings.refresh()
    assert constants.C_RETENTION_DAYS == 90

    # Unchanged file: not applied again
    with patch.object(web_settings, 'apply') as apply:
        web_settings.refresh()
    apply.assert_not_called()

    # Removed by another worker
    os.remove(app_file)
    web_settings.refresh()
    assert constants.C_RETENTION_DAYS == web_settings.get_base('C_RETENTION_DAYS')



def test_invalid_value_of_the_file(app_file, caplog):
    """Edited by hand: the start stops; a running process logs it and keeps the value without the web app"""

    app_file.write_text(json.dumps({'C_MAX_PARALLEL_STEPS': 0, 'C_RETENTION_DAYS': 30}))

    with pytest.raises(settings_check.Invalid_Setting_Error, match='C_MAX_PARALLEL_STEPS = 0'):
        web_settings.load_at_start()

    web_settings._applied = None
    web_settings.refresh()
    assert constants.C_MAX_PARALLEL_STEPS == web_settings.get_base('C_MAX_PARALLEL_STEPS')
    assert constants.C_RETENTION_DAYS == 30
    assert 'C_MAX_PARALLEL_STEPS = 0' in caplog.text



def test_every_setting_of_the_web_app_has_a_check():
    """The checks of the start (settings_check) also check the values of the web app"""

    assert set(web_settings.EDITABLE) <= set(settings_check.CHECKS)
    assert set(web_settings.SECURITY) <= set(web_settings.get_names())
    assert not set(web_settings.EDITABLE) & set(web_settings.SECURITY)
