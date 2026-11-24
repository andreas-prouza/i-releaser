"""
Processing mode and processing service, changed in the web app.
See docs/features/processing-settings-in-web-app.md and docs/features/processing-service-auto-start.md

The settings changed in the web app are stored in etc/app.json (C_APP_SETTINGS_FILE).
The mode there overrides C_PROCESSING_MODE of etc/settings.py, which overrides the default in etc/constants.py.
The file is read for each start of a stage, so all workers of the web app use a new mode without a restart.
"""

import json
import logging
import os
import re
import subprocess
import sys
import time

from etc import constants
from modules import files, errors


PROCESSING_MODES = ['thread', 'service']
SERVICE_ACTIONS = ['start', 'stop', 'restart']

# serviceapp/service waits up to 10 seconds for the service to stop
SERVICE_COMMAND_TIMEOUT = 60

SOURCE_WEB_APP = 'web app'
SOURCE_SETTINGS = 'etc/settings.py'
SOURCE_DEFAULT = 'default'

# Shown in the log as the user who started the service
AUTO_START_USER = 'auto start'
# Seconds the auto start waits until the started service listens
AUTO_START_WAIT_SECONDS = 10

ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*m')



def get_old_settings_file() -> str:
    """Where earlier versions stored the settings: etc/web_settings.json"""
    return os.path.join(os.path.dirname(constants.C_APP_SETTINGS_FILE), 'web_settings.json')



def take_over_old_settings_file() -> None:
    """
    Renames etc/web_settings.json to etc/app.json, so an installation keeps its processing mode.
    Called at the start of the web app, by each worker: only one of them can rename it.
    """

    old_file = get_old_settings_file()

    if os.path.exists(constants.C_APP_SETTINGS_FILE) or not os.path.exists(old_file):
        return

    try:
        os.rename(old_file, constants.C_APP_SETTINGS_FILE)
    except FileNotFoundError:
        # Taken over by another worker meanwhile
        return

    logging.info(f"{old_file} has been renamed to {constants.C_APP_SETTINGS_FILE}")



def read_app_settings() -> dict:

    if not os.path.exists(constants.C_APP_SETTINGS_FILE):
        return {}

    with open(constants.C_APP_SETTINGS_FILE) as f:
        settings = json.load(f)

    if not isinstance(settings, dict):
        raise errors.App_Error(f"{constants.C_APP_SETTINGS_FILE} has to contain a JSON object")

    return settings



def write_app_settings(settings: dict) -> None:
    """Written to a new file with a unique name first (files.writeJson), so a reader never sees a half written file
    and two processes don't write the same temporary file"""

    files.writeJson(settings, constants.C_APP_SETTINGS_FILE)



def change_app_setting(key: str, value) -> object:
    """Read, change and write under a lock: the processes of the web app may change settings at the same time.

    Returns the old value"""

    with files.lock(f"{constants.C_APP_SETTINGS_FILE}.lock"):
        settings = read_app_settings()
        old_value = settings.get(key)
        settings[key] = value
        write_app_settings(settings)

    return old_value



def remove_app_setting(key: str) -> object:
    """Removes a setting of the web app under the same lock (docs/features/settings-in-web-app.md). Returns the old value"""

    with files.lock(f"{constants.C_APP_SETTINGS_FILE}.lock"):
        settings = read_app_settings()
        old_value = settings.pop(key, None)
        write_app_settings(settings)

    return old_value



def get_processing_mode() -> str:

    mode = read_app_settings().get('C_PROCESSING_MODE', constants.C_PROCESSING_MODE)

    if mode not in PROCESSING_MODES:
        raise errors.App_Error(f"C_PROCESSING_MODE '{mode}' is invalid. Valid modes are: {', '.join(PROCESSING_MODES)}")

    return mode



def get_processing_mode_source() -> str:
    """Where the current mode comes from"""

    if 'C_PROCESSING_MODE' in read_app_settings():
        return SOURCE_WEB_APP

    # Loaded by etc/constants.py, if the file exists. No import here: without the file,
    # `from etc import settings` raises a plain ImportError (etc is a namespace package).
    settings = sys.modules.get('etc.settings')

    return SOURCE_SETTINGS if hasattr(settings, 'C_PROCESSING_MODE') else SOURCE_DEFAULT



def set_processing_mode(mode: str, user: str|None) -> None:

    # Imported here: the module is imported by meta_file
    from modules.db import processing_job_data
    from modules.job_status import Status as Job_Status

    if mode not in PROCESSING_MODES:
        raise errors.Invalid_Input_Error(f"Invalid processing mode '{mode}'. Valid modes are: {', '.join(PROCESSING_MODES)}")

    if mode == 'thread':
        queued = processing_job_data.get_jobs(status=[Job_Status.QUEUED])
        if queued:
            raise errors.Conflict_Error(f"{len(queued)} stage(s) are waiting in the queue of the processing service. "
                                        "Start the service to run them, or remove them from the queue first.")

    old_mode = change_app_setting('C_PROCESSING_MODE', mode) or constants.C_PROCESSING_MODE

    logging.info(f"Processing mode changed from '{old_mode}' to '{mode}' by {user}")



def get_service_auto_start() -> bool:
    """Off, until it's turned on in the web app"""
    return read_app_settings().get('C_SERVICE_AUTO_START', False) is True



def set_service_auto_start(enabled: bool, user: str|None) -> None:

    change_app_setting('C_SERVICE_AUTO_START', enabled)

    logging.info(f"Auto start of the processing service turned {'on' if enabled else 'off'} by {user}")



def is_service_auto_start_paused() -> bool:
    """After `serviceapp/service stop` until the next start"""
    return os.path.exists(constants.C_SERVICE_STOPPED_FILE)



def ensure_service_running() -> bool:
    """
    Auto start: starts the processing service, if it's turned on, the mode is 'service' and the service is not running.
    Called by each worker of the web app at its start and every C_SERVICE_WATCHDOG_INTERVAL seconds.

    Returns:
        bool: True if the service has been started
    """

    # Imported here: the module is imported by meta_file
    from modules import processing_service

    if not get_service_auto_start() or get_processing_mode() != 'service' or is_service_auto_start_paused():
        return False

    if processing_service.notify():
        return False

    # Only one worker starts the service. The others don't wait: the next check is soon enough.
    lock = processing_service.try_lock(f"{constants.C_SERVICE_LOCK_FILE}.start")
    if lock is None:
        return False

    try:
        # Meanwhile started by another worker, or stopped by an admin
        if processing_service.notify() or is_service_auto_start_paused():
            return False

        logging.warning("Processing service is not running: auto start")
        control_service('start', AUTO_START_USER)

        # serviceapp/service waits only 1 second. Loading the modules and scripts may take longer.
        # The lock is kept meanwhile, so no other worker starts a second one.
        end = time.monotonic() + AUTO_START_WAIT_SECONDS
        while not processing_service.notify():
            if time.monotonic() > end:
                logging.error(f"Auto start of the processing service failed. See {constants.C_LOCAL_BASE_DIR}/log/service_nohup.log and service.log")
                break
            time.sleep(0.5)

    finally:
        lock.close()

    return True



def control_service(action: str, user: str|None) -> str:
    """Runs serviceapp/service start|stop|restart. Returns its output.

    The command runs in its own session, so the service keeps running when the web app ends.
    """

    if action not in SERVICE_ACTIONS:
        raise errors.Invalid_Input_Error(f"Invalid action '{action}'. Valid actions are: {', '.join(SERVICE_ACTIONS)}")

    logging.info(f"Processing service: {action} by {user}")

    script = os.path.join(constants.C_LOCAL_BASE_DIR, 'serviceapp', 'service')

    try:
        result = subprocess.run([script, action], stdin=subprocess.DEVNULL, capture_output=True, text=True, errors='replace',
                                timeout=SERVICE_COMMAND_TIMEOUT, start_new_session=True,
                                # The service runs with the same Python as the web app
                                env={**os.environ, 'I_RELEASER_PYTHON': sys.executable})
    except subprocess.TimeoutExpired as e:
        raise errors.App_Error(f"serviceapp/service {action} did not end within {SERVICE_COMMAND_TIMEOUT} seconds") from e

    output = ANSI_ESCAPE.sub('', result.stdout + result.stderr).strip()
    logging.info(f"Processing service: {action}: {output}")

    return output
