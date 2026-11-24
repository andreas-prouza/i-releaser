"""The settings are checked at the start (docs/features/core-redesign.md, step 7)"""
import pytest

from modules import settings_check
from etc import constants


def defaults() -> dict:
    return {name: getattr(constants, name) for name in dir(constants) if name.startswith('C_')}


def test_the_defaults_are_valid():
    assert settings_check.check(defaults(), set()) == []


@pytest.mark.parametrize('name, value', [
    ('C_MAX_PARALLEL_STEPS', 0),
    ('C_COMMAND_TIMEOUT_SECONDS', -1),
    ('C_LOGIN_MAX_FAILURES', '2'),
    ('C_2FA_POLICY', 'sometimes'),
    ('C_PROCESSING_MODE', 'Service'),
    ('C_EXTERNAL_URL', 'ireleaser.example.com'),
    ('C_EXTERNAL_URL', 'https://ireleaser.example.com/path'),
    ('C_CSP_REPORT_ONLY', 'False'),
    ('C_SERVICE_HEARTBEAT_TIMEOUT', 5),
])
def test_invalid_value(name, value):

    with pytest.raises(settings_check.Invalid_Setting_Error) as error:
        settings_check.check({**defaults(), name: value}, set())

    assert name in str(error.value)


def test_unknown_name_is_a_warning():

    warnings = settings_check.check(defaults(), {'C_LOGIN_MAX_FAILURE', 'C_LOGIN_MAX_FAILURES'})

    assert len(warnings) == 1 and 'C_LOGIN_MAX_FAILURE ' in warnings[0]


def test_every_setting_with_a_number_or_choice_is_checked():
    """A new setting is added to settings_check.CHECKS"""

    unchecked = {name for name, value in defaults().items()
                 if isinstance(value, (int, float, bool)) and name not in settings_check.CHECKS}

    assert unchecked == set()


def test_web_app_does_not_start_with_an_invalid_setting():

    from web_server import Web_Server

    server = Web_Server(settings="C_MAX_PARALLEL_STEPS = 0\n")
    try:
        with pytest.raises(Exception, match='Web app did not start'):
            server.start()
        assert 'C_MAX_PARALLEL_STEPS = 0 has to be at least 1' in server.read_logs()
    finally:
        server.close()
