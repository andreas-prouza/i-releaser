import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta

from fastapi import Request

SESSION_DIR = 'sessions'
SESSION_LIFETIME = timedelta(hours=1)

if not os.path.exists(SESSION_DIR):
    os.makedirs(SESSION_DIR)

def get_session_filepath(session_id: str) -> str:
    """Constructs the full path for a session file."""
    return os.path.join(SESSION_DIR, f"{session_id}.json")

def get_session(request: Request) -> dict:
    """
    Retrieves session data from a JSON file based on the session_id in the request cookie.
    If the session is expired or doesn't exist, it returns an empty dictionary.
    """
    session_id = request.cookies.get("session_id")
    if not session_id:
        return {}

    session_file = get_session_filepath(session_id)
    if not os.path.exists(session_file):
        return {}

    try:
        with open(session_file, 'r') as f:
            session_data = json.load(f)

        last_update = datetime.fromisoformat(session_data.get("last-update"))
        if datetime.now() - last_update > SESSION_LIFETIME:
            # Session expired, delete the file
            os.remove(session_file)
            return {}

        # Return the actual session data payload
        return session_data.get("session-data", {})
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logging.error(f"Error reading session file {session_file}: {e}")
        # If file is corrupt, treat as non-existent
        if os.path.exists(session_file):
            os.remove(session_file)
        return {}

def save_session(session_id: str, data: dict):
    """Saves the session data to a JSON file."""
    session_file = get_session_filepath(session_id)
    session_data = {
        "last-update": datetime.now().isoformat(),
        "session_id": session_id,
        "session-data": data
    }
    try:
        with open(session_file, 'w') as f:
            json.dump(session_data, f, indent=4)
    except IOError as e:
        logging.error(f"Could not write to session file {session_file}: {e}")

def create_session() -> tuple[str, dict]:
    """
    Creates a new session, returning a new session_id and an empty session data dictionary.
    """
    session_id = str(uuid.uuid4())
    session_data = {}
    save_session(session_id, session_data)
    return session_id, session_data

def update_session(request: Request, data: dict) -> str:
    """
    Updates an existing session with new data. If no session exists, a new one is created.
    Returns the session_id.
    """
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        logging.info(f"No session_id found, creating a new one: {session_id}")

    save_session(session_id, data)
    return session_id

class SessionManager:
    """A helper class to attach to the request state."""
    def __init__(self, request: Request):
        self._request = request
        self.session_id = self._request.cookies.get("session_id")
        self.data = {}
        self._modified = False

    async def load(self):
        """Loads session data or creates a new session if none exists."""
        if self.session_id:
            self.data = get_session(self._request)
        
        if not self.session_id or not self.data:
            self.session_id, self.data = create_session()
            # Mark as modified to ensure the cookie gets set on the response
            self._modified = True

    def save(self):
        """Saves the session data if it has been modified."""
        if self._modified:
            save_session(self.session_id, self.data)

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
        if self._modified:
            response.set_cookie(
                key="session_id",
                value=self.session_id,
                httponly=True,
                max_age=int(SESSION_LIFETIME.total_seconds())
            )