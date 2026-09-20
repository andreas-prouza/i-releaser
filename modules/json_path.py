"""
Minimal JSONPath support for addressing a single value in a json structure.

Supported syntax (concrete paths only, no wildcards or filters):
  $.a.b          object keys
  $.a[0].b       list index
  $['my key']    quoted key (single or double quotes)
The leading `$` is optional.
"""
import re
from typing import Any, List


class InvalidJsonPathException(Exception):
  pass


MISSING = object()

_TOKEN = re.compile(r"""
    \.(?P<key>[A-Za-z0-9_\-]+)             # .key
  | \[(?P<index>\d+)\]                     # [0]
  | \[(?P<q>['"])(?P<qkey>.*?)(?P=q)\]     # ['key'] or ["key"]
""", re.VERBOSE)



def parse(path: str) -> List[str|int]:
  """
  Splits a path into its keys (str) and list indices (int).

  Raises:
      InvalidJsonPathException: If the path is not a string or uses unsupported syntax.
  """

  if not isinstance(path, str) or not path.strip():
    raise InvalidJsonPathException(f"Invalid JSONPath: {path!r}")

  rest = path.strip()
  if rest.startswith('$'):
    rest = rest[1:]
  elif not rest.startswith(('.', '[')):
    rest = '.' + rest

  parts: List[str|int] = []
  pos = 0

  while pos < len(rest):
    match = _TOKEN.match(rest, pos)
    if match is None:
      raise InvalidJsonPathException(f"Unsupported JSONPath syntax at position {pos} of '{path}'")
    if match.group('key') is not None:
      parts.append(match.group('key'))
    elif match.group('index') is not None:
      parts.append(int(match.group('index')))
    else:
      parts.append(match.group('qkey'))
    pos = match.end()

  if not parts:
    raise InvalidJsonPathException(f"JSONPath '{path}' does not address a value")

  return parts



def normalize(path: str) -> str:
  """Canonical form of a path, so that e.g. `a.b` and `$['a']['b']` compare equal."""

  return '$' + ''.join(f"[{p}]" if isinstance(p, int) else f"['{p}']" for p in parse(path))



def get_value(data: Any, path: str) -> Any:
  """Returns the value at path or `MISSING` if it does not exist."""

  current = data
  for part in parse(path):
    if isinstance(part, int):
      if not isinstance(current, list) or part >= len(current):
        return MISSING
    elif not isinstance(current, dict) or part not in current:
      return MISSING
    current = current[part]

  return current



def set_value(data: dict, path: str, value: Any) -> None:
  """
  Sets the value at path and creates missing dicts/lists on the way.

  Raises:
      InvalidJsonPathException: If an existing element on the way has the wrong type
                                or a list index would leave a gap.
  """

  parts = parse(path)
  current = data

  for i, part in enumerate(parts):
    last = i == len(parts) - 1

    if isinstance(part, int):
      if not isinstance(current, list):
        raise InvalidJsonPathException(f"'{path}': expected a list before index [{part}]")
      if part > len(current):
        raise InvalidJsonPathException(f"'{path}': index [{part}] is out of range (list has {len(current)} items)")
      if part == len(current):
        current.append(None)
    else:
      if not isinstance(current, dict):
        raise InvalidJsonPathException(f"'{path}': expected an object before key '{part}'")

    if last:
      current[part] = value
      return

    child = current[part] if (isinstance(part, int) or part in current) else None
    if not isinstance(child, (dict, list)):
      if child is not None:
        raise InvalidJsonPathException(f"'{path}': can't descend into a non-container value at '{part}'")
      child = [] if isinstance(parts[i + 1], int) else {}
      current[part] = child
    current = child
