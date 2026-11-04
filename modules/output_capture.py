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



class _Thread_Stream:
  """Replaces sys.stdout or sys.stderr: writes to the buffer of the current thread, if it has one"""


  def __init__(self, original: TextIO):
    self.original = original
    self.buffers: dict[int, TextIO] = {}


  def write(self, text: str) -> int:
    return self.buffers.get(threading.get_ident(), self.original).write(text)


  def flush(self) -> None:
    self.buffers.get(threading.get_ident(), self.original).flush()


  def __getattr__(self, name: str):
    return getattr(self.original, name)



def _install() -> None:

  global _active_captures, _original_streams

  with _lock:
    if _active_captures == 0:
      _original_streams = (sys.stdout, sys.stderr)
      sys.stdout = _Thread_Stream(sys.stdout)
      sys.stderr = _Thread_Stream(sys.stderr)

    _active_captures += 1



def _uninstall() -> None:

  global _active_captures

  with _lock:
    _active_captures -= 1

    if _active_captures == 0:
      sys.stdout, sys.stderr = _original_streams



@contextlib.contextmanager
def capture(stdout: TextIO, stderr: TextIO):
  """
  Args:
      stdout: Gets stdout of the current thread, and its log records
      stderr: Gets stderr of the current thread
  """

  thread_id = threading.get_ident()

  handler = logging.StreamHandler(stream=stdout)
  handler.addFilter(lambda record: record.thread == thread_id)

  root_logger = logging.getLogger()
  root_logger.addHandler(handler)
  _install()

  sys.stdout.buffers[thread_id] = stdout
  sys.stderr.buffers[thread_id] = stderr

  try:
    yield

  finally:
    del sys.stdout.buffers[thread_id]
    del sys.stderr.buffers[thread_id]

    _uninstall()
    root_logger.removeHandler(handler)
