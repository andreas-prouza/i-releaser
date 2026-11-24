"""
Captures what the current thread writes to stdout, stderr and the log.
All other threads of the process keep writing to the original streams.
"""
import contextlib
import logging
import sys
import threading
from typing import TextIO


_lock = threading.Lock()
_active_captures = 0
_original_streams = None
# The replacements of sys.stdout and sys.stderr while a capture is active
_thread_streams = None



class _Thread_Stream:
  """Replaces sys.stdout or sys.stderr: writes to the innermost buffer of the current thread, if it has one"""


  def __init__(self, original: TextIO):
    self.original = original
    # Per thread a stack: captures can be nested (a SCRIPT step which runs a SCRIPT sub-step)
    self.buffers: dict[int, list[TextIO]] = {}


  def _target(self) -> TextIO:
    stack = self.buffers.get(threading.get_ident())
    return stack[-1] if stack else self.original


  def write(self, text: str) -> int:
    return self._target().write(text)


  def flush(self) -> None:
    self._target().flush()


  def __getattr__(self, name: str):
    return getattr(self.original, name)



# Per thread the stack of its active captures, to give the log records only to the innermost one
_captures: dict[int, list[object]] = {}



def _push(stacks: dict, thread_id: int, item) -> None:
  stacks.setdefault(thread_id, []).append(item)



def _remove(stacks: dict, thread_id: int, item) -> None:
  """Removes the item (by identity) from the stack of the thread"""

  stack = stacks.get(thread_id, [])

  for i in range(len(stack) - 1, -1, -1):
    if stack[i] is item:
      del stack[i]
      break

  if not stack:
    stacks.pop(thread_id, None)



def _is_innermost(thread_id: int, token: object) -> bool:
  stack = _captures.get(thread_id)
  return bool(stack) and stack[-1] is token



def _install() -> None:

  global _active_captures, _original_streams, _thread_streams

  with _lock:
    if _active_captures == 0:
      _original_streams = (sys.stdout, sys.stderr)
      _thread_streams = (_Thread_Stream(sys.stdout), _Thread_Stream(sys.stderr))
      sys.stdout, sys.stderr = _thread_streams

    _active_captures += 1



def _uninstall() -> None:

  global _active_captures, _thread_streams

  with _lock:
    _active_captures -= 1

    if _active_captures == 0:
      sys.stdout, sys.stderr = _original_streams
      _thread_streams = None



@contextlib.contextmanager
def capture(stdout: TextIO, stderr: TextIO):
  """
  Captures can be nested in a thread: the innermost one gets the output, the outer one again after the inner has ended.
  See docs/bugfixes/nested-script-output-capture.md.

  Args:
      stdout: Gets stdout of the current thread, and its log records
      stderr: Gets stderr of the current thread
  """

  thread_id = threading.get_ident()
  token = object()

  handler = logging.StreamHandler(stream=stdout)
  handler.addFilter(lambda record: record.thread == thread_id and _is_innermost(thread_id, token))
  root_logger = logging.getLogger()

  _install()
  # The streams of this capture, even if sys.stdout is replaced meanwhile
  out, err = _original_streams_of_capture()

  try:
    _push(out.buffers, thread_id, stdout)
    _push(err.buffers, thread_id, stderr)
    _push(_captures, thread_id, token)
    root_logger.addHandler(handler)

    yield

  finally:
    root_logger.removeHandler(handler)
    _remove(_captures, thread_id, token)
    _remove(out.buffers, thread_id, stdout)
    _remove(err.buffers, thread_id, stderr)
    _uninstall()



def _original_streams_of_capture() -> tuple[_Thread_Stream, _Thread_Stream]:

  with _lock:
    return _thread_streams
