"""
Checks the settings of etc/settings.py at the start of the web app and the processing service
(docs/features/core-redesign.md, step 7; docs/bugfixes/minor-code-defects-2026-11.md, item 14).

An invalid value stops the start with a message which names the setting. A name which isn't a setting of i-Releaser
(e.g. a typo) is logged as warning: it would be ignored without notice otherwise.
"""
import ast
import logging
import os
import re
from typing import Callable

from etc import constants


class Invalid_Setting_Error(Exception):
    pass



def _int(minimum: int) -> Callable:
    def check(value) -> str|None:
        if not isinstance(value, int) or isinstance(value, bool):
            return "has to be a whole number"
        if value < minimum:
            return f"has to be at least {minimum}"
        return None
    return check



def _number(minimum: float, above: bool=False) -> Callable:
    def check(value) -> str|None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return "has to be a number"
        if value < minimum or (above and value == minimum):
            return f"has to be {'more than' if above else 'at least'} {minimum}"
        return None
    return check



def _one_of(*values) -> Callable:
    def check(value) -> str|None:
        return None if value in values else f"has to be one of {', '.join(repr(v) for v in values)}"
    return check



def _bool(value) -> str|None:
    return None if isinstance(value, bool) else "has to be True or False"



def _url(value) -> str|None:
    if value == '':
        return None
    return None if isinstance(value, str) and re.fullmatch(r'https?://[^/\s]+', value) else "has to be '' or scheme and host, e.g. 'https://ireleaser.example.com' (without path)"



def _text(value) -> str|None:
    return None if isinstance(value, str) and value != '' else "has to be a text"



CHECKS: dict[str, Callable] = {
  'C_DB_BACKUP_COUNT': _int(1),
  'C_MAX_CUSTOM_DATA_SIZE': _int(1),
  'C_MAX_COMPILE_LIST_SIZE': _int(1),
  'C_COMMAND_TIMEOUT_SECONDS': _int(0),
  'C_MAX_PARALLEL_STEPS': _int(1),
  'C_LOGIN_MAX_FAILURES': _int(1),
  'C_LOGIN_CLIENT_MAX_FAILURES': _int(1),
  'C_LOGIN_BLOCK_MINUTES': _number(0, above=True),
  'C_LOGIN_TIMEOUT_SECONDS': _int(1),
  'C_LOGIN_MAX_PARALLEL': _int(1),
  'C_EXTERNAL_URL': _url,
  'C_TOKEN_MAX_DAYS': _int(0),
  'C_WATCH_SESSION_CHECK_SECONDS': _number(0, above=True),
  'C_HEALTH_MIN_FREE_MB': _int(0),
  'C_AUDIT_RETENTION_DAYS': _int(0),
  'C_RETENTION_DAYS': _int(0),
  'C_RETENTION_ARCHIVE': _bool,
  'C_RETENTION_MAX_PER_RUN': _int(1),
  'C_LOG_MAX_MB': _int(0),
  'C_LOG_BACKUPS': _int(0),
  'C_2FA_POLICY': _one_of('off', 'optional', 'admins', 'required'),
  'C_2FA_STEP_UP_MINUTES': _number(0, above=True),
  'C_2FA_MAX_FAILURES': _int(1),
  'C_PROCESSING_MODE': _one_of('thread', 'service'),
  'C_SERVICE_WATCHDOG_INTERVAL': _number(0, above=True),
  'C_SERVICE_POLL_INTERVAL': _number(0, above=True),
  'C_SERVICE_MAX_PARALLEL_JOBS': _int(1),
  'C_SERVICE_HEARTBEAT_INTERVAL': _number(0, above=True),
  'C_SERVICE_HEARTBEAT_TIMEOUT': _number(0, above=True),
  'C_SCHEDULE_MAX_DELAY_MINUTES': _number(0),
  'C_GIT_BRANCH_PRODUCTION': _text,
  'C_GIT_BRANCH_RELEASE': _text,
  'C_CSP_REPORT_ONLY': _bool,
}



def get_known_names() -> set[str]:
    """The settings of i-Releaser: the names which etc/constants.py defines"""

    with open(os.path.join(os.path.dirname(os.path.abspath(constants.__file__)), 'constants.py'), encoding='utf-8') as f:
        tree = ast.parse(f.read())

    return {target.id for node in tree.body if isinstance(node, ast.Assign) for target in node.targets
            if isinstance(target, ast.Name) and target.id.startswith('C_')}



def get_set_names() -> set[str]:
    """The names of etc/settings.py, empty without the file"""

    try:
        from etc import settings
    except ImportError:
        # No etc/settings.py (`etc` is a namespace package: ImportError, not ModuleNotFoundError)
        return set()

    return {name for name in vars(settings) if name.startswith('C_')}



def check(values: dict|None=None, set_names: set[str]|None=None) -> list[str]:
    """
    Args:
        values: The settings (default: etc/constants.py with etc/settings.py)
        set_names: The names of etc/settings.py (default: read from it)

    Returns:
        list: Warnings (unknown names)

    Raises:
        Invalid_Setting_Error: With all invalid values
    """

    values = values if values is not None else {name: getattr(constants, name) for name in dir(constants) if name.startswith('C_')}
    set_names = set_names if set_names is not None else get_set_names()

    errors = []
    for name, check_value in CHECKS.items():
        if name in values:
            problem = check_value(values[name])
            if problem:
                errors.append(f"{name} = {values[name]!r} {problem}")

    interval, timeout = values.get('C_SERVICE_HEARTBEAT_INTERVAL'), values.get('C_SERVICE_HEARTBEAT_TIMEOUT')
    if isinstance(interval, (int, float)) and isinstance(timeout, (int, float)) and timeout <= interval:
        errors.append(f"C_SERVICE_HEARTBEAT_TIMEOUT ({timeout}) has to be more than C_SERVICE_HEARTBEAT_INTERVAL ({interval}), otherwise every job is aborted")

    if errors:
        raise Invalid_Setting_Error("Invalid settings in etc/settings.py: " + '; '.join(errors))

    known = get_known_names()
    return [f"Setting {name} in etc/settings.py is not a setting of i-Releaser (a typo?). It's ignored." for name in sorted(set_names - known)]



def check_at_start() -> None:
    """Logs the warnings; an invalid value raises (the start stops). Then the values of the web app (etc/app.json) count."""

    for warning in check():
        logging.warning(warning)

    # docs/features/settings-in-web-app.md
    from modules import web_settings
    web_settings.load_at_start()
