"""
API tokens (table api_tokens, docs/features/api-v2.md#tokens): several per user, each with a name, a scope and an expiry.
Only the SHA-256 hash of a token is stored. Times are UTC, ISO 8601.
"""
import datetime

from modules.db import app_sqlite


READ = 'read'
WRITE = 'write'
SCOPES = (READ, WRITE)

COLUMNS = "id, user, name, masked, scope, created_at, expires_at, last_used_at, legacy"



def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')



def add(user: str, name: str, key_hash: str, masked: str, scope: str, expires_at: str|None, created_at: str|None=None,
        last_used_at: str|None=None, legacy: bool=False) -> int|None:
    """
    Returns:
        int|None: The id; None if a token with this hash exists already (a migrated one)
    """

    with app_sqlite.get_db_connection() as conn:
        c = conn.execute("""INSERT OR IGNORE INTO api_tokens (user, name, key_hash, masked, scope, created_at, expires_at, last_used_at, legacy)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                         (user.lower(), name, key_hash, masked, scope, created_at or now(), expires_at, last_used_at, int(legacy)))
        conn.commit()
        return c.lastrowid if c.rowcount == 1 else None



def get_by_hash(key_hash: str) -> dict|None:

    with app_sqlite.get_db_connection() as conn:
        row = conn.execute(f"SELECT {COLUMNS} FROM api_tokens WHERE key_hash = ?", (key_hash,)).fetchone()

    return _as_dict(row)



def get(token_id: int) -> dict|None:

    with app_sqlite.get_db_connection() as conn:
        row = conn.execute(f"SELECT {COLUMNS} FROM api_tokens WHERE id = ?", (token_id,)).fetchone()

    return _as_dict(row)



def _as_dict(row) -> dict|None:

    if row is None:
        return None

    data = dict(row)
    data['legacy'] = bool(data['legacy'])
    return data



def get_of_user(user: str) -> list[dict]:

    with app_sqlite.get_db_connection() as conn:
        rows = conn.execute(f"SELECT {COLUMNS} FROM api_tokens WHERE user = ? ORDER BY id", (user.lower(),)).fetchall()

    return [_as_dict(row) for row in rows]



def get_all() -> list[dict]:

    with app_sqlite.get_db_connection() as conn:
        rows = conn.execute(f"SELECT {COLUMNS} FROM api_tokens ORDER BY user, id").fetchall()

    return [_as_dict(row) for row in rows]



def name_exists(user: str, name: str) -> bool:

    with app_sqlite.get_db_connection() as conn:
        return conn.execute("SELECT 1 FROM api_tokens WHERE user = ? AND name = ?", (user.lower(), name)).fetchone() is not None



def delete(token_id: int) -> bool:

    with app_sqlite.get_db_connection() as conn:
        c = conn.execute("DELETE FROM api_tokens WHERE id = ?", (token_id,))
        conn.commit()
        return c.rowcount == 1



def delete_of_user(user: str, name: str|None=None) -> int:
    """All tokens of the user, or the ones with this name. Returns the number."""

    sql, params = "DELETE FROM api_tokens WHERE user = ?", [user.lower()]
    if name is not None:
        sql += " AND name = ?"
        params.append(name)

    with app_sqlite.get_db_connection() as conn:
        c = conn.execute(sql, params)
        conn.commit()
        return c.rowcount



def update(token_id: int, **values) -> None:
    """last_used_at, expires_at, legacy"""

    allowed = {'last_used_at', 'expires_at', 'legacy'}
    assert set(values) <= allowed, values

    with app_sqlite.get_db_connection() as conn:
        conn.execute(f"UPDATE api_tokens SET {', '.join(f'{key} = ?' for key in values)} WHERE id = ?", (*values.values(), token_id))
        conn.commit()
