"""
Failed logins (docs/bugfixes/login-can-disable-ibm-i-profiles.md)

* Per client address: failures within the last C_LOGIN_BLOCK_MINUTES (C_LOGIN_CLIENT_MAX_FAILURES). The block ends by itself.
* Per user: failed IBM i sign-ons in a row, without time limit. The IBM i counts them the same way (system value QMAXSIGN)
  until the next successful sign-on. So the block of a user only ends with a successful login before it, or by an admin.
"""

import time

from etc import constants
from modules.db import app_sqlite


USER_KEY = 'user:'
CLIENT_KEY = 'client:'
# Wrong codes of the two-factor authentication: no IBM i sign-on, but they must not be guessed
CODE_KEY = 'code:'



def _user_key(user: str) -> str:
    return f"{USER_KEY}{user.lower()}"


def _client_key(client: str) -> str:
    return f"{CLIENT_KEY}{client}"



def is_user_blocked(user: str) -> bool:
    """The user had C_LOGIN_MAX_FAILURES failed IBM i sign-ons in a row"""

    with app_sqlite.get_db_connection() as conn:
        count = conn.execute("SELECT count(*) FROM login_failures WHERE key = ?", (_user_key(user),)).fetchone()[0]

    return count >= constants.C_LOGIN_MAX_FAILURES



def is_client_blocked(client: str) -> bool:
    """The client address had C_LOGIN_CLIENT_MAX_FAILURES failed logins within C_LOGIN_BLOCK_MINUTES"""

    since = time.time() - constants.C_LOGIN_BLOCK_MINUTES * 60

    with app_sqlite.get_db_connection() as conn:
        count = conn.execute("SELECT count(*) FROM login_failures WHERE key = ? AND failed_at > ?", (_client_key(client), since)).fetchone()[0]

    return count >= constants.C_LOGIN_CLIENT_MAX_FAILURES



def is_blocked(user: str, client: str) -> bool:
    """A user, or a client address, is blocked after too many failed logins"""

    return is_client_blocked(client) or is_user_blocked(user)



def add_failure(user: str, client: str, sign_on_tried: bool=True) -> None:
    """
    Args:
        sign_on_tried: The password has been checked by the IBM i (and was wrong). Only these count for the user,
            as only they count for QMAXSIGN. Every failure counts for the client.
    """

    now = time.time()
    keys = [_client_key(client)] + ([_user_key(user)] if sign_on_tried else [])

    with app_sqlite.get_db_connection() as conn:
        conn.execute("DELETE FROM login_failures WHERE key LIKE ? AND failed_at < ?", (f"{CLIENT_KEY}%", now - constants.C_LOGIN_BLOCK_MINUTES * 60))
        conn.executemany("INSERT INTO login_failures (key, failed_at) VALUES (?, ?)", [(key, now) for key in keys])
        conn.commit()



def clear_failures(user: str, client: str) -> None:
    """After a successful login"""

    with app_sqlite.get_db_connection() as conn:
        conn.executemany("DELETE FROM login_failures WHERE key = ?", [(_user_key(user),), (_client_key(client),)])
        conn.commit()



def _code_key(user: str) -> str:
    return f"{CODE_KEY}{user.lower()}"



def is_code_blocked(user: str) -> bool:
    """C_2FA_MAX_FAILURES wrong codes of the two-factor authentication within C_LOGIN_BLOCK_MINUTES"""

    since = time.time() - constants.C_LOGIN_BLOCK_MINUTES * 60

    with app_sqlite.get_db_connection() as conn:
        count = conn.execute("SELECT count(*) FROM login_failures WHERE key = ? AND failed_at > ?", (_code_key(user), since)).fetchone()[0]

    return count >= constants.C_2FA_MAX_FAILURES



def add_code_failure(user: str) -> None:

    now = time.time()

    with app_sqlite.get_db_connection() as conn:
        conn.execute("DELETE FROM login_failures WHERE key = ? AND failed_at < ?", (_code_key(user), now - constants.C_LOGIN_BLOCK_MINUTES * 60))
        conn.execute("INSERT INTO login_failures (key, failed_at) VALUES (?, ?)", (_code_key(user), now))
        conn.commit()



def clear_code_failures(user: str) -> None:

    with app_sqlite.get_db_connection() as conn:
        conn.execute("DELETE FROM login_failures WHERE key = ?", (_code_key(user),))
        conn.commit()



def unblock_user(user: str) -> bool:
    """
    Returns:
        bool: False if the user had no failed logins
    """

    with app_sqlite.get_db_connection() as conn:
        c = conn.execute("DELETE FROM login_failures WHERE key = ?", (_user_key(user),))
        conn.commit()
        return c.rowcount > 0



def get_blocked_users() -> list[dict]:
    """Users who are blocked, with the number and the time (epoch) of the last failure"""

    with app_sqlite.get_db_connection() as conn:
        rows = conn.execute("SELECT key, count(*) AS failures, max(failed_at) AS last_failure FROM login_failures WHERE key LIKE ? GROUP BY key HAVING count(*) >= ? ORDER BY key",
                            (f"{USER_KEY}%", constants.C_LOGIN_MAX_FAILURES)).fetchall()

    return [{'user': row['key'][len(USER_KEY):], 'failures': row['failures'], 'last_failure': row['last_failure']} for row in rows]
