"""
Audit log of security events (docs/features/audit-log.md).

Rows are only added. Each row contains the hash of the row before it, so a changed or deleted row is detected by
`verify_chain` (not a rewrite of the whole table). Optionally each event is also written as a JSON line to
C_AUDIT_FILE, e.g. for a SIEM.
"""
import datetime
import hashlib
import json
import logging

from etc import constants
from modules import files
from modules.db import app_sqlite


EVENTS = ['login', 'login_failed', 'login_blocked', 'login_unblocked', 'logout',
          'token_created', 'token_deleted', 'token_revoked',
          '2fa_enabled', '2fa_disabled', '2fa_reset', '2fa_recovery_codes',
          'permissions_changed', 'setting_changed', 'log_viewed', 'data_removed']

FIRST_HASH = '0' * 64

# Keys of details which are never stored
SECRET_KEYS = {'password', 'pwd', 'token', 'key', 'secret', 'code', 'recovery_codes'}



def _hash(prev_hash: str, row: dict) -> str:
    content = json.dumps([prev_hash, row['time'], row['user'], row['client'], row['event'], row['object'], row['details'], row['result']],
                         ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(content.encode('utf-8')).hexdigest()



def _without_secrets(details):

    if isinstance(details, dict):
        return {k: ('***' if k.lower() in SECRET_KEYS else _without_secrets(v)) for k, v in details.items()}
    if isinstance(details, list):
        return [_without_secrets(v) for v in details]
    return details



def add(event: str, user: str|None=None, client: str|None=None, object: str|None=None, details: dict|None=None, result: str='ok') -> None:
    """Adds an event. Never raises: an audit entry which can't be written is logged, the action isn't stopped by it."""

    try:
        row = {
            'time': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
            'user': user,
            'client': client,
            'event': event,
            'object': object,
            'details': json.dumps(_without_secrets(details), ensure_ascii=False, sort_keys=True) if details else None,
            'result': result,
        }

        with app_sqlite.get_db_connection() as conn:
            c = conn.cursor()
            # The hash of the last row and the new row together: two events at the same time get a chain
            c.execute("BEGIN IMMEDIATE")
            last = c.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
            prev_hash = last['hash'] if last else FIRST_HASH
            row['prev_hash'] = prev_hash
            row['hash'] = _hash(prev_hash, row)
            c.execute("INSERT INTO audit_log (time, user, client, event, object, details, result, prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (row['time'], row['user'], row['client'], row['event'], row['object'], row['details'], row['result'], row['prev_hash'], row['hash']))
            conn.commit()

        _write_file(row)

    except Exception as e:
        logging.exception(f"Audit event {event} of {user=} could not be written: {e}")



def _write_file(row: dict) -> None:

    file = getattr(constants, 'C_AUDIT_FILE', '')
    if not file:
        return

    line = json.dumps({k: row[k] for k in ['time', 'user', 'client', 'event', 'object', 'result']} | {'details': json.loads(row['details']) if row['details'] else None},
                      ensure_ascii=False)
    with files.lock(f"{file}.lock"):
        with open(file, 'a', encoding='utf-8') as f:
            f.write(line + '\n')



def get_entries(limit: int=1000) -> list[dict]:
    """The newest entries, newest first"""

    with app_sqlite.get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    return [dict(row) for row in rows]



def verify_chain() -> int|None:
    """
    Returns:
        int|None: The id of the first row which doesn't fit to the one before (changed or deleted rows), None if the chain is complete
    """

    with app_sqlite.get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()

    prev_hash = None

    for row in rows:
        row = dict(row)
        # The first row after a clean up (retention) starts the chain
        if prev_hash is not None and row['prev_hash'] != prev_hash:
            return row['id']
        if _hash(row['prev_hash'], row) != row['hash']:
            return row['id']
        prev_hash = row['hash']

    return None



def remove_older_than(days: int) -> int:
    """Retention (C_AUDIT_RETENTION_DAYS). Returns the number of removed rows."""

    if not days:
        return 0

    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat(timespec='seconds')

    with app_sqlite.get_db_connection() as conn:
        c = conn.execute("DELETE FROM audit_log WHERE time < ?", (since,))
        conn.commit()
        return c.rowcount
