from modules import files
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta

from fastapi import Request
from starlette.concurrency import run_in_threadpool

from etc import global_cfg

SESSION_DIR = 'sessions'
# A session ends after this time without a request ...
SESSION_LIFETIME = timedelta(hours=1)
# ... and after this time in any case
SESSION_MAX_LIFETIME = timedelta(hours=12)
# A request of the user extends the session; its file is written at most this often for that
TOUCH_INTERVAL = timedelta(minutes=1)
COOKIE_NAME = 'session_id'

_SESSION_ID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')

if not os.path.exists(SESSION_DIR):
    os.makedirs(SESSION_DIR)


def is_valid_session_id(session_id: str|None) -> bool:
    """The session id comes from the cookie and is part of a file name"""
    return session_id is not None and _SESSION_ID.fullmatch(session_id) is not None


def get_session_filepath(session_id: str) -> str:
    """Constructs the full path for a session file."""
    return os.path.join(SESSION_DIR, f"{session_id}.json")


def is_expired(session_data: dict) -> bool:

    now = datetime.now()
    last_update = datetime.fromisoformat(session_data['last-update'])
    # Sessions of older versions have no creation time
    create_time = datetime.fromisoformat(session_data.get('create-time') or session_data['last-update'])

    return now - last_update > SESSION_LIFETIME or now - create_time > SESSION_MAX_LIFETIME


def load_session_file(session_id: str) -> dict|None:
    """
    Returns:
        dict: Content of the session file, None if the session doesn't exist or has expired
    """

    session_file = get_session_filepath(session_id)

    if not os.path.exists(session_file):
        return None

    try:
        session_data = files.getJson(session_file, retry=True)

        if is_expired(session_data):
            # Session expired, delete the file
            delete_session(session_id)
            return None

        return session_data

    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logging.error(f"Error reading a session file: {e}")
        # If file is corrupt, treat as non-existent
        return None


def save_session(session_id: str, data: dict, create_time: str|None=None, create: bool=False) -> bool:
    """
    Saves the session data to a JSON file.

    Args:
        create: A new session. Otherwise only a session which exists is written:
            a session which has been ended (logout, expired) is never created again by a request which was running at that time.

    Returns:
        bool: False if the session doesn't exist (anymore) or can't be written
    """

    session_file = get_session_filepath(session_id)

    if not create and not os.path.exists(session_file):
        return False

    now = datetime.now().isoformat()
    session_data = {
        "create-time": create_time or now,
        "last-update": now,
        "session-data": data
    }
    try:
        files.writeJson(session_data, session_file)
        return True
    except OSError as e:
        logging.error(f"Could not write a session file: {e}")
        return False


def delete_session(session_id: str) -> None:

    try:
        os.remove(get_session_filepath(session_id))
    except FileNotFoundError:
        pass


def delete_expired_sessions() -> int:
    """
    Removes the files of sessions which have expired.

    Returns:
        int: Number of deleted sessions
    """

    deleted = 0

    for file_name in os.listdir(SESSION_DIR):

        session_id = file_name.removesuffix('.json')

        if not is_valid_session_id(session_id):
            continue

        if load_session_file(session_id) is None:
            delete_session(session_id)
            deleted += 1

    logging.info(f"Deleted {deleted} expired sessions")
    return deleted


class SessionManager:
    """
    The session of a request (request.state.session).

    The file is only written if the data has changed, or (touch) to extend the session at most every TOUCH_INTERVAL.
    A new session gets a file only when it has data, e.g. after the login. See docs/bugfixes/logout-undone-by-concurrent-request.md.
    """
    def __init__(self, request: Request):
        self._request = request
        self.session_id = self._request.cookies.get(COOKIE_NAME)
        self.data = {}
        self.create_time = None
        self.last_update: str|None = None
        self._modified = False
        self._destroyed = False
        # A new session id: its file doesn't exist yet, and the browser needs the cookie
        self._new = False
        self._touched = False
        # A request with an API token doesn't need a session
        self.transient = False

    async def load(self):
        """Loads session data or creates a new session if none exists."""

        # A file: not on the event loop
        session_file = await run_in_threadpool(load_session_file, self.session_id) if is_valid_session_id(self.session_id) else None

        if session_file is not None:
            self.data = session_file.get('session-data', {})
            self.create_time = session_file.get('create-time')
            self.last_update = session_file.get('last-update')

        if not self.data:
            self.session_id = str(uuid.uuid4())
            self.data = {}
            self.create_time = None
            self.last_update = None
            self._new = True

    def regenerate(self):
        """Gives the session a new id, so an id which has been known before the login is worthless."""
        delete_session(self.session_id)
        self.session_id = str(uuid.uuid4())
        self.create_time = None
        self._new = True
        self._modified = True

    def destroy(self):
        """Ends the session (logout)"""
        delete_session(self.session_id)
        self.data = {}
        self._destroyed = True

    def touch(self):
        """A request of the user: the session doesn't end for the next SESSION_LIFETIME"""
        self._touched = True

    def needs_touch(self) -> bool:

        if not self._touched or self.last_update is None:
            return False

        try:
            return datetime.now() - datetime.fromisoformat(self.last_update) >= TOUCH_INTERVAL
        except ValueError:
            return True

    def save(self):
        """Saves the session data if it has been modified (or the session has to be extended)."""

        if self._destroyed or self.transient:
            return

        if not self.data:
            # An empty session doesn't need a file
            if self._modified and not self._new:
                delete_session(self.session_id)
            return

        if not self._modified and not self.needs_touch():
            return

        if not save_session(self.session_id, self.data, self.create_time, create=self._new):
            logging.info("The session has ended meanwhile, it is not saved")

    def __contains__(self, key):
        return key in self.data

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
        self._modified = True

    def __delitem__(self, key):
        del self.data[key]
        self._modified = True

    def get(self, key, default=None):
        return self.data.get(key, default)

    def pop(self, key, default=None):
        if key in self.data:
            self._modified = True
        return self.data.pop(key, default)

    def set_cookie(self, response):
        """Sets the session cookie for a new session, deletes it after the logout."""

        if self._destroyed:
            response.delete_cookie(key=COOKIE_NAME, httponly=True, samesite='lax')
            return

        if self._new and self.data and not self.transient:
            # Without max_age: the browser forgets it when it's closed. The server ends the session after
            # SESSION_LIFETIME without a request, and after SESSION_MAX_LIFETIME in any case.
            response.set_cookie(
                key=COOKIE_NAME,
                value=self.session_id,
                httponly=True,
                samesite='lax',
                secure=getattr(global_cfg, 'C_COOKIE_SECURE', True),
            )
