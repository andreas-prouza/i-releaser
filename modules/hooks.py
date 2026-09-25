"""
Lifecycle hooks of a deployment

A workflow can define python functions (from the `scripts/` folder) which are called on specific events:

  "hooks": {
    "stage_finished": ["jira.on_event"]
  }

Each function is called with:

  func(event: str, meta_file: Meta_File, stage_obj: Stage|None) -> None

`stage_obj` is only set for stage events.
Errors of a hook are logged only. They never affect the deployment.
"""
from __future__ import annotations

import importlib
import logging
from enum import Enum
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
  from modules.meta_file import Meta_File
  from modules.stages import Stage



class InvalidHookException(Exception):
  pass



class Event(str, Enum):
  DEPLOYMENT_CREATED = 'deployment_created'
  DEPLOYMENT_FINISHED = 'deployment_finished'
  DEPLOYMENT_CANCELED = 'deployment_canceled'
  STAGE_STARTED = 'stage_started'
  STAGE_FINISHED = 'stage_finished'
  STAGE_FAILED = 'stage_failed'
  CUSTOM_DATA_CHANGED = 'custom_data_changed'



def validate(hooks: dict) -> None:
  """
  Raises:
      InvalidHookException: If hooks is not a dict of {event: ['filename.function_name', ...]}
  """

  if not isinstance(hooks, dict):
    raise InvalidHookException("'hooks' needs to be a dict of {event: ['filename.function_name', ...]}")

  valid_events = [e.value for e in Event]

  for event, handlers in hooks.items():

    if event not in valid_events:
      raise InvalidHookException(f"Hook event '{event}' is invalid. Valid events are: {valid_events}")

    if not isinstance(handlers, list):
      raise InvalidHookException(f"Hooks of event '{event}' need to be a list")

    for handler in handlers:
      if not isinstance(handler, str) or len(handler.split('.')) != 2 or '' in handler.split('.'):
        raise InvalidHookException(f"Hook '{handler}' of event '{event}' has not the correct format: 'filename.function_name' (without '.py' in filename)")



def resolve(execute: str) -> Callable:
  """Returns the function of 'filename.function_name' from the scripts/ folder"""

  module_name, function_name = execute.split('.')
  module = importlib.import_module(f"scripts.{module_name}")
  return getattr(module, function_name)



def emit(event: Event, meta_file: Meta_File, stage: Stage|None=None) -> None:
  """Calls all hooks of the deployment's workflow for this event"""

  workflow = getattr(meta_file, 'workflow', None)
  hooks = getattr(workflow, 'hooks', None) or {}

  for execute in hooks.get(event.value, []):
    try:
      logging.info(f"Run hook {execute} for event '{event.value}'")
      resolve(execute)(event.value, meta_file, stage)

    except Exception as e:
      logging.error(f"Hook {execute} for event '{event.value}' failed: {e}")
      logging.exception(e, stack_info=True)
