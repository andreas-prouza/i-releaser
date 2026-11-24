"""
Two-factor authentication of the users (table user_mfa, docs/features/two-factor-authentication.md).
Changes which decide (a code is used, a recovery code is used) are one conditional statement: two requests can't use the same code.
"""
import datetime
import json

from modules.db import app_sqlite



def get(user: str) -> dict|None:
    """
    Returns:
        dict: user, secret, enabled (bool), created_at, last_step, recovery_codes (number of unused codes); None if not set up
    """

    with app_sqlite.get_db_connection() as conn:
        row = conn.execute("SELECT * FROM user_mfa WHERE user = ?", (user.lower(),)).fetchone()

    if row is None:
        return None

    return {'user': row['user'], 'secret': row['secret'], 'enabled': bool(row['enabled']), 'created_at': row['created_at'],
            'last_step': row['last_step'], 'recovery_codes': len(json.loads(row['recovery_codes']))}



def is_enabled(user: str) -> bool:
    mfa = get(user)
    return mfa is not None and mfa['enabled']



def start_setup(user: str, secret: str) -> None:
    """A new secret, not active until it's confirmed with a code. Replaces a setup which hasn't been confirmed."""

    with app_sqlite.get_db_connection() as conn:
        c = conn.execute("UPDATE user_mfa SET secret = ?, created_at = ?, last_step = NULL WHERE user = ? AND enabled = 0",
                         (secret, datetime.datetime.now(datetime.timezone.utc).isoformat(), user.lower()))
        if c.rowcount == 0:
            conn.execute("INSERT OR IGNORE INTO user_mfa (user, secret, enabled, created_at) VALUES (?, ?, 0, ?)",
                         (user.lower(), secret, datetime.datetime.now(datetime.timezone.utc).isoformat()))
        conn.commit()



def enable(user: str, step: int, recovery_hashes: list[str]) -> bool:
    """Activates the setup with the step of the code which confirmed it"""

    with app_sqlite.get_db_connection() as conn:
        c = conn.execute("UPDATE user_mfa SET enabled = 1, last_step = ?, recovery_codes = ? WHERE user = ? AND enabled = 0",
                         (step, json.dumps(recovery_hashes), user.lower()))
        conn.commit()
        return c.rowcount == 1



def use_step(user: str, step: int) -> bool:
    """
    Remembers the time step of an accepted code.

    Returns:
        bool: False if a code of this or a later step has been used already (the code is used twice)
    """

    with app_sqlite.get_db_connection() as conn:
        c = conn.execute("UPDATE user_mfa SET last_step = ? WHERE user = ? AND enabled = 1 AND (last_step IS NULL OR last_step < ?)",
                         (step, user.lower(), step))
        conn.commit()
        return c.rowcount == 1



def has_recovery_code(user: str, code_hash: str) -> bool:

    with app_sqlite.get_db_connection() as conn:
        row = conn.execute("SELECT recovery_codes FROM user_mfa WHERE user = ? AND enabled = 1", (user.lower(),)).fetchone()

    return row is not None and code_hash in json.loads(row['recovery_codes'])



def use_recovery_code(user: str, code_hash: str) -> bool:
    """Removes the recovery code. False if it isn't valid (or has been used already)."""

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT recovery_codes FROM user_mfa WHERE user = ? AND enabled = 1", (user.lower(),)).fetchone()

        if row is None:
            return False

        codes = json.loads(row['recovery_codes'])
        if code_hash not in codes:
            return False

        codes.remove(code_hash)
        c.execute("UPDATE user_mfa SET recovery_codes = ? WHERE user = ?", (json.dumps(codes), user.lower()))
        conn.commit()
        return True



def set_recovery_codes(user: str, recovery_hashes: list[str]) -> None:

    with app_sqlite.get_db_connection() as conn:
        conn.execute("UPDATE user_mfa SET recovery_codes = ? WHERE user = ? AND enabled = 1", (json.dumps(recovery_hashes), user.lower()))
        conn.commit()



def remove(user: str) -> bool:
    """Turns off the two-factor authentication of the user (also: reset by an admin)"""

    with app_sqlite.get_db_connection() as conn:
        c = conn.execute("DELETE FROM user_mfa WHERE user = ?", (user.lower(),))
        conn.commit()
        return c.rowcount == 1



def get_enabled_users() -> list[str]:

    with app_sqlite.get_db_connection() as conn:
        return [row['user'] for row in conn.execute("SELECT user FROM user_mfa WHERE enabled = 1 ORDER BY user")]
