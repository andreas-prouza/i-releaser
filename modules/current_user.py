"""
User of the current request or job.

It's bound to the current context, so concurrent requests can't see each other's user.
A thread doesn't inherit the context: run it with `contextvars.copy_context().run`.
Without a user (None) nothing is permitted.
"""
from contextvars import ContextVar


_current_user: ContextVar[str|None] = ContextVar('current_user', default=None)



def get_user() -> str|None:
  return _current_user.get()



def set_user(user: str|None) -> None:
  _current_user.set(user.upper() if user else None)
