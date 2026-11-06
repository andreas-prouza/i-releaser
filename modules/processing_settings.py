"""
Processing mode and processing service, changed in the web app.
See docs/features/processing-settings-in-web-app.md

The mode changed in the web app is stored in etc/web_settings.json.
It overrides C_PROCESSING_MODE of etc/settings.py, which overrides the default in etc/constants.py.
The file is read for each start of a stage, so all workers of the web app use a new mode without a restart.
"""

import json
import logging
import os
import re
import subprocess
import sys

from etc import constants
from modules import errors


PROCESSING_MODES = ['thread', 'service']
SERVICE_ACTIONS = ['start', 'stop', 'restart']

# serviceapp/service waits up to 10 seconds for the service to stop
SERVICE_COMMAND_TIMEOUT = 60

SOURCE_WEB_APP = 'web app'
SOURCE_SETTINGS = 'etc/settings.py'
SOURCE_DEFAULT = 'default'

ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*m')



def read_web_settings() -> dict:

  if not os.path.exists(constants.C_WEB_SETTINGS_FILE):
    return {}

  with open(constants.C_WEB_SETTINGS_FILE) as f:
    settings = json.load(f)

  if not isinstance(settings, dict):
    raise errors.App_Error(f"{constants.C_WEB_SETTINGS_FILE} has to contain a JSON object")

  return settings



def write_web_settings(settings: dict) -> None:
  """Written to a new file first, so a reader never sees a half written file"""

  tmp_file = f"{constants.C_WEB_SETTINGS_FILE}.tmp"
  with open(tmp_file, 'w') as f:
    json.dump(settings, f, indent=2)
  os.replace(tmp_file, constants.C_WEB_SETTINGS_FILE)



def get_processing_mode() -> str:

  mode = read_web_settings().get('C_PROCESSING_MODE', constants.C_PROCESSING_MODE)

  if mode not in PROCESSING_MODES:
    raise errors.App_Error(f"C_PROCESSING_MODE '{mode}' is invalid. Valid modes are: {', '.join(PROCESSING_MODES)}")

  return mode



def get_processing_mode_source() -> str:
  """Where the current mode comes from"""

  if 'C_PROCESSING_MODE' in read_web_settings():
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

  settings = read_web_settings()
  old_mode = settings.get('C_PROCESSING_MODE', constants.C_PROCESSING_MODE)
  settings['C_PROCESSING_MODE'] = mode
  write_web_settings(settings)

  logging.info(f"Processing mode changed from '{old_mode}' to '{mode}' by {user}")



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
  except subprocess.TimeoutExpired:
    raise errors.App_Error(f"serviceapp/service {action} did not end within {SERVICE_COMMAND_TIMEOUT} seconds")

  output = ANSI_ESCAPE.sub('', result.stdout + result.stderr).strip()
  logging.info(f"Processing service: {action}: {output}")

  return output
