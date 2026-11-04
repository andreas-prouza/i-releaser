import time

from etc import constants
from modules.db import app_sqlite



def _get_keys(user: str, client: str) -> tuple[str, str]:
    return f"user:{user}", f"client:{client}"



def is_blocked(user: str, client: str) -> bool:
    """A user, or a client address, is blocked after too many failed logins"""

    since = time.time() - constants.C_LOGIN_BLOCK_MINUTES * 60

    with app_sqlite.get_db_connection() as conn:
        for key in _get_keys(user, client):
            count = conn.execute("SELECT count(*) FROM login_failures WHERE key = ? AND failed_at > ?", (key, since)).fetchone()[0]
            if count >= constants.C_LOGIN_MAX_FAILURES:
                return True

    return False



def add_failure(user: str, client: str) -> None:

    now = time.time()

    with app_sqlite.get_db_connection() as conn:
        conn.execute("DELETE FROM login_failures WHERE failed_at < ?", (now - constants.C_LOGIN_BLOCK_MINUTES * 60,))
        conn.executemany("INSERT INTO login_failures (key, failed_at) VALUES (?, ?)", [(key, now) for key in _get_keys(user, client)])
        conn.commit()



def clear_failures(user: str, client: str) -> None:

    with app_sqlite.get_db_connection() as conn:
        conn.executemany("DELETE FROM login_failures WHERE key = ?", [(key,) for key in _get_keys(user, client)])
        conn.commit()
