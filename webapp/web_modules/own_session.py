
import time, logging
import contextvars
import asyncio



#session_lock = asyncio.Lock()


async def get_session(sessions_context: contextvars.ContextVar, id) -> {}:

 # async with session_lock:

  sessions = sessions_context.get()
  
  if id not in sessions:
    sessions[id] = {"id": id, "last-update": int(time.time())}
    sessions_context.set(sessions)

  return sessions[id]



async def update_session(sessions_context: contextvars.ContextVar, id, session):

  #async with session_lock:
  sessions = sessions_context.get()
  session['last-update'] = int(time.time())
  sessions[id] = session
  logging.debug(f"Update {session=}")
  sessions_context.set(sessions)

  return