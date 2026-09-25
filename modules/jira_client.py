"""
Reports deployments to Jira

* Jira Cloud:       Deployments API. Deployments are shown in the development panel of the issue.
* Jira Data Center: Remote links (and optional comments) on the issue.
                    Data Center has no deployments API for 3rd party tools.

Each mapped stage of a workflow is a Jira environment.
The Jira state is derived from the stage status, so each report can be repeated safely.

Configuration: etc/jira.json (see etc/examples/jira.json and docs/jira.md)
"""
from __future__ import annotations

import datetime
import logging
import os
import re
import threading
import time
from typing import TYPE_CHECKING

import requests

from etc import constants
from modules import files, json_path
from modules.meta_file_status import Meta_file_status
from modules.stage_status import Status as Stage_Status

if TYPE_CHECKING:
  from modules.meta_file import Meta_File
  from modules.stages import Stage



class JiraException(Exception):
  pass



C_ENV_CLIENT_SECRET = 'I_RELEASER_JIRA_CLIENT_SECRET'
C_ENV_TOKEN = 'I_RELEASER_JIRA_TOKEN'

C_DEFAULT_API_URL = 'https://api.atlassian.com'
C_DEFAULT_ISSUE_KEY_PATHS = ['$.jira.ticket']
C_DEFAULT_COMMENT_EVENTS = ['stage_finished', 'stage_failed', 'deployment_canceled']

ISSUE_KEY = re.compile(r'^[A-Z][A-Z0-9_]+-[0-9]+$')

STAGE_STATE = {
  Stage_Status.NEW: 'pending',
  Stage_Status.READY: 'pending',
  Stage_Status.PREPARE: 'in_progress',
  Stage_Status.IN_PREPERATION: 'in_progress',
  Stage_Status.IN_PROCESS: 'in_progress',
  Stage_Status.FAILED: 'failed',
  Stage_Status.FINISHED: 'successful',
}



class _Cache:
  """Shared by all stage threads of a worker process"""
  lock = threading.RLock()
  config: dict|None = None
  config_hash: str|None = None
  token: str|None = None
  token_expires: float = 0
  cloud_id: str|None = None
  update_sequence: int = 0



def load_config() -> dict|None:
  """Returns the content of etc/jira.json or None if it doesn't exist. It's reloaded when the file changes."""

  if not os.path.isfile(constants.C_JIRA_CONFIG):
    return None

  file_hash = files.get_file_hash(constants.C_JIRA_CONFIG)

  with _Cache.lock:
    if file_hash != _Cache.config_hash:
      _Cache.config = files.getJson(constants.C_JIRA_CONFIG, retry=True) or {}
      _Cache.config_hash = file_hash
      # Credentials may have changed
      _Cache.token = None
      _Cache.cloud_id = None
    return _Cache.config



def report(event: str, meta_file: Meta_File, stage: Stage|None=None, state: str|None=None) -> bool:
  """
  Reports the deployment to Jira.
  A stage event reports the environment of its stage, other events all mapped environments of the workflow.

  Args:
      event (str): Name of the hook event
      state (str, optional): Jira state to report instead of the one derived from the stage status

  Returns:
      bool: False if nothing has been reported (not configured, stage not mapped, no issue key)

  Raises:
      JiraException: Invalid configuration or Jira responded with an error
      requests.RequestException: Jira is not reachable
  """

  config = load_config()
  if not config or not config.get('enabled', True):
    logging.debug("Jira: integration is not configured or disabled")
    return False

  environments = get_environments(config, meta_file.workflow.name)
  reports = get_reports(event, meta_file, stage, environments, state)
  if len(reports) == 0:
    logging.debug(f"Jira: no mapped environment for event '{event}' of workflow '{meta_file.workflow.name}'")
    return False

  issue_keys = get_issue_keys(config, meta_file.custom_data)
  if len(issue_keys) == 0:
    logging.info(f"Jira: no issue key in custom data of deployment {meta_file.id}")
    return False

  mode = config.get('mode', 'cloud')

  if mode == 'cloud':
    send_to_cloud(config, meta_file, reports, issue_keys)
  elif mode == 'datacenter':
    send_to_datacenter(config, event, meta_file, reports, issue_keys)
  else:
    raise JiraException(f"Jira: mode '{mode}' is invalid. Valid modes are: cloud, datacenter")

  return True



def get_environments(config: dict, workflow_name: str|None) -> dict[str, dict]:
  """Returns the mapping {stage name: environment} of the workflow"""

  for name, workflow in (config.get('workflows') or {}).items():
    if name.lower() == (workflow_name or '').lower():
      return workflow.get('environments') or {}

  return {}



def get_issue_keys(config: dict, custom_data: dict|None) -> list[str]:
  """Reads the issue keys from custom data. A value may be a single key, a comma separated string or a list."""

  keys = []

  for path in config.get('issue_key_paths') or C_DEFAULT_ISSUE_KEY_PATHS:

    value = json_path.get_value(custom_data or {}, path)
    if value is json_path.MISSING or value is None:
      continue

    values = value if isinstance(value, list) else str(value).split(',')

    for v in values:
      key = str(v).strip().upper()
      if key == '':
        continue
      if not ISSUE_KEY.match(key):
        logging.warning(f"Jira: '{v}' in custom data {path} is not a valid issue key")
        continue
      if key not in keys:
        keys.append(key)

  return keys



def get_state(event: str, meta_file: Meta_File, stage: Stage) -> str:

  status = Stage_Status(stage.status) if isinstance(stage.status, str) else stage.status

  if event == 'stage_failed':
    return 'failed'

  if status != Stage_Status.FINISHED and meta_file.status == Meta_file_status.CANCELED:
    return 'cancelled'

  return STAGE_STATE.get(status, 'unknown')



def get_reports(event: str, meta_file: Meta_File, stage: Stage|None, environments: dict[str, dict], state: str|None=None) -> list[tuple[dict, Stage, str]]:
  """Returns a list of (environment, stage, state) which needs to be reported"""

  if stage is not None:
    stages = [stage] if stage.name in environments else []
  else:
    # Latest stage of each mapped stage name
    latest = {}
    for s in meta_file.stages:
      if s.name in environments:
        latest[s.name] = s
    stages = list(latest.values())

  return [(environments[s.name], s, state or get_state(event, meta_file, s)) for s in stages]



def get_environment(environment: dict, stage: Stage) -> dict:

  env_id = str(environment.get('id') or stage.name)
  return {
    'id': env_id,
    'displayName': environment.get('display_name') or env_id,
    'type': environment.get('type') or 'unmapped',
  }



def get_base_url(config: dict) -> str:

  base_url = (config.get('i_releaser_url') or '').rstrip('/')
  if not base_url:
    raise JiraException("Jira: 'i_releaser_url' is missing in the configuration")
  return base_url



def get_display_name(meta_file: Meta_File) -> str:
  return f"{meta_file.project} {meta_file.deploy_version}"



def get_timeout(config: dict) -> tuple[float, float]:
  return (5, config.get('timeout_seconds', 10))



def next_update_sequence() -> int:
  """Increasing number, so Jira ignores updates which arrive out of order"""

  with _Cache.lock:
    _Cache.update_sequence = max(int(time.time() * 1000), _Cache.update_sequence + 1)
    return _Cache.update_sequence



#######################################################################
# Jira Cloud
#######################################################################


def get_api_url(config: dict) -> str:
  return ((config.get('cloud') or {}).get('api_url') or C_DEFAULT_API_URL).rstrip('/')



def get_cloud_token(config: dict) -> str:
  """OAuth 2.0 client credentials token. It's cached until it expires."""

  cloud = config.get('cloud') or {}

  with _Cache.lock:

    if _Cache.token and _Cache.token_expires > time.time():
      return _Cache.token

    client_secret = os.environ.get(C_ENV_CLIENT_SECRET) or cloud.get('client_secret')
    if not cloud.get('client_id') or not client_secret:
      raise JiraException(f"Jira: 'cloud.client_id' and 'cloud.client_secret' (or env {C_ENV_CLIENT_SECRET}) are required")

    r = requests.post(f"{get_api_url(config)}/oauth/token", json={
      'audience': 'api.atlassian.com',
      'grant_type': 'client_credentials',
      'client_id': cloud['client_id'],
      'client_secret': client_secret,
    }, timeout=get_timeout(config))

    if not r.ok:
      raise JiraException(f"Jira: getting OAuth token failed with HTTP {r.status_code}: {r.text}")

    data = r.json()
    _Cache.token = data['access_token']
    _Cache.token_expires = time.time() + int(data.get('expires_in', 900)) - 60
    return _Cache.token



def get_cloud_id(config: dict) -> str:

  cloud = config.get('cloud') or {}

  if cloud.get('cloud_id'):
    return cloud['cloud_id']

  with _Cache.lock:

    if _Cache.cloud_id:
      return _Cache.cloud_id

    site = (cloud.get('site') or '').rstrip('/')
    if not site:
      raise JiraException("Jira: 'cloud.site' or 'cloud.cloud_id' is required")
    if not site.startswith('http'):
      site = f"https://{site}"

    r = requests.get(f"{site}/_edge/tenant_info", timeout=get_timeout(config))
    if not r.ok:
      raise JiraException(f"Jira: getting cloud id of {site} failed with HTTP {r.status_code}: {r.text}")

    _Cache.cloud_id = r.json()['cloudId']
    return _Cache.cloud_id



def get_cloud_deployment(config: dict, meta_file: Meta_File, environment: dict, stage: Stage, state: str, issue_keys: list[str]) -> dict:

  base_url = get_base_url(config)
  workflow_name = meta_file.workflow.name

  return {
    'schemaVersion': '1.0',
    'deploymentSequenceNumber': meta_file.id,
    'updateSequenceNumber': next_update_sequence(),
    'associations': [{'associationType': 'issueIdOrKeys', 'values': issue_keys}],
    'displayName': get_display_name(meta_file),
    'url': f"{base_url}/show_details/{meta_file.id}",
    'description': f"Workflow '{workflow_name}', stage '{stage.name}'",
    'lastUpdated': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
    'label': str(meta_file.deploy_version),
    'state': state,
    'pipeline': {'id': workflow_name, 'displayName': workflow_name, 'url': f"{base_url}/workflows"},
    'environment': get_environment(environment, stage),
  }



def send_to_cloud(config: dict, meta_file: Meta_File, reports: list[tuple[dict, Stage, str]], issue_keys: list[str]) -> dict:

  url = f"{get_api_url(config)}/jira/deployments/0.1/cloud/{get_cloud_id(config)}/bulk"
  body = {
    'deployments': [get_cloud_deployment(config, meta_file, env, stage, state, issue_keys) for env, stage, state in reports],
    'providerMetadata': {'product': f"i-Releaser {constants.C_APP_VERSION}"},
  }

  r = requests.post(url, json=body, headers={'Authorization': f"Bearer {get_cloud_token(config)}"}, timeout=get_timeout(config))

  if r.status_code == 401:
    with _Cache.lock:
      _Cache.token = None

  if not r.ok:
    raise JiraException(f"Jira: sending deployment failed with HTTP {r.status_code}: {r.text}")

  result = r.json() if r.content else {}

  for rejected in result.get('rejectedDeployments') or []:
    logging.warning(f"Jira: deployment has been rejected: {rejected}")

  if result.get('unknownIssueKeys'):
    logging.warning(f"Jira: unknown issue keys: {result['unknownIssueKeys']}")

  logging.info(f"Jira: reported deployment {meta_file.id} for {issue_keys}: {[(get_environment(e, s)['id'], state) for e, s, state in reports]}")
  return result



#######################################################################
# Jira Data Center
#######################################################################


def get_remote_link(config: dict, meta_file: Meta_File, environment: dict, stage: Stage, state: str) -> dict:

  env = get_environment(environment, stage)

  return {
    # Same globalId updates the existing link
    'globalId': f"i-releaser:{meta_file.id}:{env['id']}",
    'application': {'type': 'i-releaser', 'name': 'i-Releaser'},
    'relationship': 'deployment',
    'object': {
      'url': f"{get_base_url(config)}/show_details/{meta_file.id}",
      'title': f"{get_display_name(meta_file)} - {env['displayName']}: {state}",
      'summary': f"Workflow '{meta_file.workflow.name}', stage '{stage.name}'",
      'status': {'resolved': state == 'successful'},
    },
  }



def get_comment(config: dict, meta_file: Meta_File, reports: list[tuple[dict, Stage, str]]) -> dict:

  lines = [f"i-Releaser deployment [{get_display_name(meta_file)}|{get_base_url(config)}/show_details/{meta_file.id}]:"]
  for environment, stage, state in reports:
    lines.append(f"* {get_environment(environment, stage)['displayName']}: *{state}* (stage {stage.name})")

  return {'body': '\n'.join(lines)}



def send_to_datacenter(config: dict, event: str, meta_file: Meta_File, reports: list[tuple[dict, Stage, str]], issue_keys: list[str]) -> None:

  dc = config.get('datacenter') or {}
  base_url = (dc.get('base_url') or '').rstrip('/')
  token = os.environ.get(C_ENV_TOKEN) or dc.get('token')

  if not base_url or not token:
    raise JiraException(f"Jira: 'datacenter.base_url' and 'datacenter.token' (or env {C_ENV_TOKEN}) are required")

  headers = {'Authorization': f"Bearer {token}"}
  requests_2_send = []

  for key in issue_keys:

    if dc.get('remote_link', True):
      for environment, stage, state in reports:
        requests_2_send.append((f"{base_url}/rest/api/2/issue/{key}/remotelink", get_remote_link(config, meta_file, environment, stage, state)))

    if event in dc.get('comment_events', C_DEFAULT_COMMENT_EVENTS):
      requests_2_send.append((f"{base_url}/rest/api/2/issue/{key}/comment", get_comment(config, meta_file, reports)))

  # Continue with other issues if one fails (e.g. unknown issue key)
  errors = []

  for url, body in requests_2_send:
    r = requests.post(url, json=body, headers=headers, timeout=get_timeout(config))
    if not r.ok:
      errors.append(f"{url}: HTTP {r.status_code}: {r.text}")

  if len(errors) > 0:
    raise JiraException(f"Jira: sending to Data Center failed: {errors}")

  logging.info(f"Jira: reported deployment {meta_file.id} for {issue_keys}: {[(get_environment(e, s)['id'], state) for e, s, state in reports]}")
