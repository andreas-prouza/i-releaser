"""
Settings which are changed in the web app (docs/features/settings-in-web-app.md).

Only the settings of the group *operation* (EDITABLE). Their value in etc/app.json overrides etc/settings.py, which
overrides the default of etc/constants.py. All processes use a change without restart: `refresh` reads etc/app.json
again when it has changed and sets the values in `etc.constants` (the web app before each request, the processing
service before each look into the queue; a job process gets the values of the service when it's forked).
"""
import ast
import functools
import logging
import os
import sys
import threading
from dataclasses import dataclass

from etc import constants
from modules import errors, processing_settings, settings_check


@dataclass(frozen=True)
class Setting:
    name: str
    # 'int', 'number', 'bool' or 'text': the field of the page
    kind: str
    description: str


# Not C_LOG_MAX_MB, C_LOG_BACKUPS: the log is rotated by etc/logger_config.py when a process starts, before etc/app.json is read
EDITABLE: dict[str, Setting] = {s.name: s for s in [
    Setting('C_RETENTION_DAYS', 'int', "Remove finished and canceled deployments after this many days without change. 0: never"),
    Setting('C_RETENTION_ARCHIVE', 'bool', "Archive a deployment in var/archive/ before it's removed"),
    Setting('C_SCHEDULE_MAX_DELAY_MINUTES', 'number', "A scheduled run which would start more minutes late isn't run"),
    Setting('C_MAX_PARALLEL_STEPS', 'int', "Steps of a parallel group which run at the same time (from the next group)"),
    Setting('C_SERVICE_MAX_PARALLEL_JOBS', 'int', "Stages which the processing service runs at the same time"),
    Setting('C_COMMAND_TIMEOUT_SECONDS', 'int', "A step which runs longer is ended (steps without timeout_seconds). 0: no limit"),
    Setting('C_HEALTH_MIN_FREE_MB', 'int', "The health check reports an error below this free space of var/ and meta/"),
    Setting('C_GIT_BRANCH_PRODUCTION', 'text', "Git branch of the production"),
    Setting('C_GIT_BRANCH_RELEASE', 'text', "Git branch of a release ({project}, {deploy_version})"),
]}

# Shown read only on the tab Security (docs/features/settings-in-web-app.md, decisions)
# C_EXTERNAL_URL: also the origin which the check against requests of other sites (CSRF) accepts
SECURITY = ['C_EXTERNAL_URL', 'C_2FA_POLICY', 'C_2FA_STEP_UP_MINUTES', 'C_2FA_MAX_FAILURES', 'C_LOGIN_MAX_FAILURES', 'C_LOGIN_CLIENT_MAX_FAILURES',
            'C_LOGIN_BLOCK_MINUTES', 'C_LOGIN_TIMEOUT_SECONDS', 'C_LOGIN_MAX_PARALLEL', 'C_TOKEN_MAX_DAYS', 'C_WATCH_SESSION_CHECK_SECONDS',
            'C_AUDIT_RETENTION_DAYS', 'C_AUDIT_FILE', 'C_CSP_REPORT_ONLY']

SOURCE_WEB_APP = processing_settings.SOURCE_WEB_APP
SOURCE_SETTINGS = processing_settings.SOURCE_SETTINGS
SOURCE_DEFAULT = processing_settings.SOURCE_DEFAULT

# The state of etc/app.json which has been applied last: (modification time, size), None without the file
_applied: tuple|None = None
_applied_lock = threading.Lock()



@functools.lru_cache(maxsize=1)
def get_defaults() -> dict:
    """The values of etc/constants.py without etc/settings.py (only those which are a literal)"""

    path = os.path.join(os.path.dirname(os.path.abspath(constants.__file__)), 'constants.py')
    with open(path, encoding='utf-8') as f:
        tree = ast.parse(f.read())

    defaults = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                defaults[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return defaults



@functools.lru_cache(maxsize=1)
def get_names() -> tuple[str, ...]:
    """All settings of i-Releaser, in the order of etc/constants.py"""

    path = os.path.join(os.path.dirname(os.path.abspath(constants.__file__)), 'constants.py')
    with open(path, encoding='utf-8') as f:
        tree = ast.parse(f.read())

    names = [target.id for node in tree.body if isinstance(node, ast.Assign) for target in node.targets
             if isinstance(target, ast.Name) and target.id.startswith('C_')]
    return tuple(dict.fromkeys(names))



def get_file_settings() -> dict:
    """The values of etc/settings.py, empty without the file"""

    # Loaded by etc/constants.py, if the file exists (see processing_settings.get_processing_mode_source)
    module = sys.modules.get('etc.settings')
    return {name: value for name, value in vars(module).items() if name.startswith('C_')} if module else {}



def get_base(name: str):
    """The value without the web app: etc/settings.py, otherwise the default"""

    file_settings = get_file_settings()
    if name in file_settings:
        return file_settings[name]
    return get_defaults().get(name)



def get_web_values() -> dict:
    """The settings of etc/app.json which may be changed in the web app"""
    return {name: value for name, value in processing_settings.read_app_settings().items() if name in EDITABLE}



def check_value(name: str, value) -> str|None:
    """None if the value is valid, otherwise the reason"""

    setting = EDITABLE.get(name)
    if setting is None:
        return "can only be changed in etc/settings.py"
    if setting.kind == 'text' and not isinstance(value, str):
        return "has to be a text"
    check = settings_check.CHECKS.get(name)
    return check(value) if check else None



def apply(web_values: dict|None=None) -> list[str]:
    """
    Sets the values of the web app in etc.constants, and the base value for those which have been reset.

    Returns:
        list: The problems of invalid values in etc/app.json (they are left out)
    """

    web_values = get_web_values() if web_values is None else web_values
    problems = []

    for name in EDITABLE:
        value = get_base(name)
        if name in web_values:
            problem = check_value(name, web_values[name])
            if problem:
                problems.append(f"{name} = {web_values[name]!r} {problem}")
            else:
                value = web_values[name]
        setattr(constants, name, value)

    return problems



def _file_state() -> tuple|None:
    try:
        stat = os.stat(constants.C_APP_SETTINGS_FILE)
    except FileNotFoundError:
        return None
    return (stat.st_mtime_ns, stat.st_size)



def refresh() -> None:
    """Applies etc/app.json again if it has changed since. Cheap: one stat of the file."""

    global _applied

    state = _file_state()
    if state == _applied:
        return

    with _applied_lock:
        if state == _applied:
            return
        try:
            problems = apply()
        except Exception as e:
            # E.g. a file which is just written by hand: tried again with the next change
            logging.error(f"Settings of {constants.C_APP_SETTINGS_FILE} not applied: {e}")
            return
        for problem in problems:
            logging.error(f"Invalid setting in {constants.C_APP_SETTINGS_FILE} is ignored: {problem}")
        _applied = state



def load_at_start() -> None:
    """
    Applies etc/app.json at the start of the web app or the processing service.

    Raises:
        settings_check.Invalid_Setting_Error: An invalid value in etc/app.json (e.g. edited by hand)
    """

    global _applied

    state = _file_state()
    problems = apply()
    if problems:
        raise settings_check.Invalid_Setting_Error(f"Invalid settings in {constants.C_APP_SETTINGS_FILE}: " + '; '.join(problems))
    _applied = state



def get_source(name: str, web_values: dict|None=None) -> str:

    web_values = get_web_values() if web_values is None else web_values
    if name in web_values:
        return SOURCE_WEB_APP
    if name in get_file_settings():
        return SOURCE_SETTINGS
    return SOURCE_DEFAULT



def change(name: str, value, user: str|None) -> object:
    """
    Stores the value in etc/app.json; this process uses it at once, the others with their next refresh.

    Returns:
        The value before

    Raises:
        errors.Invalid_Input_Error: Not a setting of the web app, or an invalid value
    """

    if isinstance(value, float) and value.is_integer() and EDITABLE.get(name) and EDITABLE[name].kind == 'int':
        value = int(value)

    problem = check_value(name, value)
    if problem:
        raise errors.Invalid_Input_Error(f"{name} {problem}")

    old = getattr(constants, name)
    processing_settings.change_app_setting(name, value)
    refresh()

    logging.info(f"Setting {name} changed from {old!r} to {value!r} by {user}")
    return old



def reset(name: str, user: str|None) -> object:
    """
    Removes the value from etc/app.json: the value of etc/settings.py or the default counts again.

    Returns:
        The value before
    """

    if name not in EDITABLE:
        raise errors.Invalid_Input_Error(f"{name} can only be changed in etc/settings.py")

    old = getattr(constants, name)
    processing_settings.remove_app_setting(name)
    refresh()

    logging.info(f"Setting {name} reset from {old!r} to {getattr(constants, name)!r} by {user}")
    return old
