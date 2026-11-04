"""
Runs steps at the same time.

A stage run and each SCRIPT step have their own scope, so the sub-steps of a script don't end the group of the stage.
The scope is bound to the context and not to IBM_i_commands, as scripts create their own instance in each function.
"""
import concurrent.futures
import contextlib
import contextvars
import logging
from typing import Callable

from etc import constants


_current_scope: contextvars.ContextVar['Scope|None'] = contextvars.ContextVar('parallel_steps_scope', default=None)



class Scope:
  """The running group of a stage run or a script"""


  def __init__(self):
    self.group: str|None = None
    self.executor: concurrent.futures.ThreadPoolExecutor|None = None
    self.futures: list[concurrent.futures.Future] = []
    self.failed = False


  def start(self, group: str|None, step: Callable[[], None]) -> None:
    """Runs the step in the background. If another group is running, it waits for its end first."""

    if self.executor is not None and group != self.group:
      self.wait()

    if self.executor is None:
      self.group = group
      self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=constants.C_MAX_PARALLEL_STEPS)

    # A thread doesn't get the context by itself (e.g. the current user). Each step needs its own copy.
    self.futures.append(self.executor.submit(contextvars.copy_context().run, self._run, step))


  def _run(self, step: Callable[[], None]) -> None:

    # Stays `new`, like the steps after a failed one which aren't run in parallel
    if self.failed:
      return

    try:
      step()
    except Exception:
      self.failed = True
      raise


  def wait(self) -> None:
    """
    Waits until all started steps have ended.

    Raises:
        Exception: The error of the first failed step. The others can be seen in the status of their step.
    """

    if self.executor is None:
      return

    self.executor.shutdown()
    errors = [future.exception() for future in self.futures if future.exception() is not None]

    self.executor = None
    self.futures = []
    self.failed = False

    if len(errors) > 0:
      raise errors[0]


  def stop(self) -> None:
    """The run has failed anyway: steps which haven't started are left out, it only waits for the running ones."""

    self.failed = True

    try:
      self.wait()
    except Exception as e:
      logging.error(f"Parallel step failed after its run has already failed: {e}")



@contextlib.contextmanager
def scope():
  """Parallel steps which are started in this block have ended when the block ends. Raises the error of a failed one."""

  current = Scope()
  token = _current_scope.set(current)

  try:
    yield

  except BaseException:
    current.stop()
    raise

  else:
    current.wait()

  finally:
    _current_scope.reset(token)



def current() -> Scope|None:
  return _current_scope.get()
