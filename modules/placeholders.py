"""
Placeholders in commands

  {stage}, {processing_step}, {meta_file[general][project]}, {meta_file[custom_data][ticket]}, ...

Only these are replaced, other braces stay as they are (`awk '{print $1}'`, `${HOME}`).
`{{` and `}}` are literal braces.

Values can come from users (custom data), so they can't change the command:
* PASE: they are quoted for the shell, depending on where in the command they are.
* QSYS: values from users may only contain harmless characters. Quoting isn't possible, as a value can be inside or outside of a CL string.
"""
import re
import shlex

from modules.deploy_action import Command_Type


class Invalid_Placeholder_Exception(Exception):
  pass


_TOKEN = re.compile(r"""
    (?P<open>\{\{)
  | (?P<close>\}\})
  | \{(?P<name>stage|processing_step|meta_file(?:\[[^\[\]{}]+\])+)\}
""", re.VERBOSE)

_KEY = re.compile(r"\[([^\[\]]+)\]")

# Values users can set
_USER_INPUT = ('meta_file[custom_data]', 'meta_file[general][commit]', 'meta_file[general][object_list]')

_SAFE_QSYS_VALUE = re.compile(r"[A-Za-z0-9$#@_./\-]*")



def _get_value(name: str, attributes: dict) -> str:

  if not name.startswith('meta_file'):
    return str(attributes[name])

  value = attributes['meta_file']

  for key in _KEY.findall(name):
    try:
      value = value[int(key)] if isinstance(value, list) else value[key]
    except (KeyError, IndexError, TypeError, ValueError):
      raise Invalid_Placeholder_Exception(f"Placeholder {{{name}}} doesn't exist") from None

  return str(value)



def _get_quote_context(text: str) -> str|None:
  """The kind of quote which is open at the end of a shell command: ', " or None"""

  quote = None
  i = 0

  while i < len(text):
    char = text[i]

    if quote is None and char == '\\':
      i += 1
    elif quote == '"' and char == '\\':
      i += 1
    elif quote is None and char in '\'"':
      quote = char
    elif char == quote:
      quote = None

    i += 1

  return quote



def _quote_for_shell(value: str, context: str|None) -> str:

  if context == "'":
    return value.replace("'", "'\"'\"'")

  if context == '"':
    return re.sub(r'([\\"$`])', r'\\\1', value)

  return shlex.quote(value)



def resolve(cmd: str, attributes: dict, environment: Command_Type) -> str:
  """
  Replaces the placeholders of a command.

  Args:
      attributes (dict): Values of stage, processing_step and meta_file

  Raises:
      Invalid_Placeholder_Exception: If a placeholder doesn't exist, or its value isn't allowed in a QSYS command
  """

  result = ''
  pos = 0

  for match in _TOKEN.finditer(cmd):

    result += cmd[pos:match.start()]
    pos = match.end()

    if match.group('open'):
      result += '{'
      continue

    if match.group('close'):
      result += '}'
      continue

    name = match.group('name')
    value = _get_value(name, attributes)

    if environment == Command_Type.PASE:
      value = _quote_for_shell(value, _get_quote_context(result))

    elif environment == Command_Type.QSYS and name.startswith(_USER_INPUT) and not _SAFE_QSYS_VALUE.fullmatch(value):
      raise Invalid_Placeholder_Exception(f"The value of {{{name}}} contains characters which are not allowed in a QSYS command")

    result += value

  return result + cmd[pos:]
