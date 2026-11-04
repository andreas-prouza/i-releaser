from modules import files
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta

from fastapi import Request

from etc import global_cfg

SESSION_DIR = 'sessions'
# A session ends after this time without a request ...
SESSION_LIFETIME = timedelta(hours=1)
# ... and after this time in any case
SESSION_MAX_LIFETIME = timedelta(hours=12)
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


def save_session(session_id: str, data: dict, create_time: str|None=None):
    """Saves the session data to a JSON file."""
    now = datetime.now().isoformat()
    session_data = {
        "create-time": create_time or now,
        "last-update": now,
        "session-data": data
    }
    try:
        files.writeJson(session_data, get_session_filepath(session_id))
    except OSError as e:
        logging.error(f"Could not write a session file: {e}")


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
    """A helper class to attach to the request state."""
    def __init__(self, request: Request):
        self._request = request
        self.session_id = self._request.cookies.get(COOKIE_NAME)
        self.data = {}
        self.create_time = None
        self._modified = False
        self._destroyed = False
        # A request with an API token doesn't need a session
        self.transient = False

    async def load(self):
        """Loads session data or creates a new session if none exists."""

        session_file = load_session_file(self.session_id) if is_valid_session_id(self.session_id) else None

        if session_file is not None:
            self.data = session_file.get('session-data', {})
            self.create_time = session_file.get('create-time')

        if not self.data:
            self.session_id = str(uuid.uuid4())
            self.data = {}
            self.create_time = None
            # Mark as modified to ensure the cookie gets set on the response
            self._modified = True

    def regenerate(self):
        """Gives the session a new id, so an id which has been known before the login is worthless."""
        delete_session(self.session_id)
        self.session_id = str(uuid.uuid4())
        self.create_time = None
        self._modified = True

    def destroy(self):
        """Ends the session (logout)"""
        delete_session(self.session_id)
        self.data = {}
        self._destroyed = True

    def save(self):
        """Saves the session data if it has been modified."""

        if not self._modified or self._destroyed or self.transient:
            return

        if self.data:
            save_session(self.session_id, self.data, self.create_time)
        else:
            # An empty session doesn't need a file, it's replaced at the next request anyway
            delete_session(self.session_id)

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
        self._modified = True
        return self.data.pop(key, default)

    def set_cookie(self, response):
        """Sets the session cookie on the response if the session is new."""

        if self._destroyed:
            response.delete_cookie(key=COOKIE_NAME, httponly=True, samesite='lax')
            return

        if self._modified and not self.transient:
            response.set_cookie(
                key=COOKIE_NAME,
                value=self.session_id,
                httponly=True,
                samesite='lax',
                secure=getattr(global_cfg, 'C_COOKIE_SECURE', False),
                max_age=int(SESSION_LIFETIME.total_seconds())
            )
