"""
Functions of `scripts/` for SCRIPT steps and hooks: 'filename.function_name' (docs/features/core-redesign.md, step 4).

Only modules of the package `scripts`, loaded when they are used: an own script with an error only fails its steps,
not the start of the web app or the processing service. Names like `os.system` can't be reached.
"""
import glob
import importlib
import logging
import os
import re
from typing import Callable


_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')



class Script_Not_Found_Exception(Exception):
  pass



def resolve(execute: str) -> Callable:
  """
  Returns:
      The function `function_name` of `scripts/filename.py`

  Raises:
      Script_Not_Found_Exception: Invalid format, no such module or function. Other errors of the module (e.g. a syntax error) are raised as they are.
  """

  parts = execute.split('.') if isinstance(execute, str) else []

  if len(parts) != 2 or not all(_NAME.fullmatch(part) for part in parts):
    raise Script_Not_Found_Exception(f"'{execute}' has not the correct format: 'filename.function_name' (without '.py' in filename)")

  module_name, function_name = parts

  # Not the internals of a module (e.g. `pre.__class__`)
  if function_name.startswith('_'):
    raise Script_Not_Found_Exception(f"Function {function_name} not found in scripts/{module_name}.py")

  try:
    module = importlib.import_module(f"scripts.{module_name}")
  except ModuleNotFoundError as e:
    if e.name in (f"scripts.{module_name}", 'scripts'):
      raise Script_Not_Found_Exception(f"Script file scripts/{module_name}.py not found") from None
    raise

  function = getattr(module, function_name, None)

  if not callable(function):
    raise Script_Not_Found_Exception(f"Function {function_name} not found in scripts/{module_name}.py")

  return function



def preload() -> dict[str, str]:
  """
  Loads all scripts once (e.g. in the processing service, so the job processes inherit them).

  Returns:
      dict: file name -> error, of the scripts which can't be loaded (they are logged and left out)
  """

  directory = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts')
  errors = {}

  for path in sorted(glob.glob(os.path.join(directory, '*.py'))):
    name = os.path.basename(path)[:-3]
    if name == '__init__' or not _NAME.fullmatch(name):
      continue
    try:
      importlib.import_module(f"scripts.{name}")
    except Exception as e:
      logging.exception(f"Script scripts/{name}.py can't be loaded: {e}")
      errors[name] = f"{type(e).__name__}: {e}"

  return errors
