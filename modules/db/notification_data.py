"""
Outbox of the notifications (table notifications, docs/features/notifications.md).

The run of a stage only adds a row. A thread of a process sends it: it claims the row with one conditional statement,
so two processes never send the same message.
"""
import datetime
import json

from modules.db import app_sqlite


PENDING = 'pending'
SENDING = 'sending'
SENT = 'sent'
FAILED = 'failed'

# A row which is 'sending' for longer belongs to a process which has ended while sending it: it's sent again
STALE_SECONDS = 600



def now(seconds: float=0) -> str:
    """UTC, ISO 8601 with seconds: the texts compare in the order of time"""

    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)).isoformat(timespec='seconds')



def add(rows: list[dict]) -> list[int]:
    """
    Args:
        rows (list[dict]): event, meta_file_id, channel, recipients (list), message (dict)
    """

    created = now()
    ids = []

    with app_sqlite.get_db_connection() as conn:
        for row in rows:
            c = conn.execute("""INSERT INTO notifications (created_at, event, meta_file_id, channel, recipients, message, status, attempts, next_attempt_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)""",
                             (created, row['event'], row.get('meta_file_id'), row['channel'], json.dumps(row.get('recipients') or []),
                              json.dumps(row['message'], default=str, ensure_ascii=False), PENDING, created))
            ids.append(c.lastrowid)
        conn.commit()

    return ids



def claim_due(limit: int=20) -> list[dict]:
    """The messages which are due (new, or their next attempt has come), claimed by this process"""

    current = now()

    with app_sqlite.get_db_connection() as conn:
        conn.execute("UPDATE notifications SET status = ? WHERE status = ? AND claimed_at < ?", (PENDING, SENDING, now(-STALE_SECONDS)))
        rows = conn.execute("SELECT * FROM notifications WHERE status = ? AND next_attempt_at <= ? ORDER BY id LIMIT ?",
                            (PENDING, current, limit)).fetchall()

        claimed = []
        for row in rows:
            c = conn.execute("UPDATE notifications SET status = ?, claimed_at = ? WHERE id = ? AND status = ?", (SENDING, current, row['id'], PENDING))
            if c.rowcount == 1:
                claimed.append(_as_dict(row))
        conn.commit()

    return claimed



def _as_dict(row) -> dict:

    data = dict(row)
    data['recipients'] = json.loads(data['recipients'] or '[]')
    data['message'] = json.loads(data['message'])
    return data



def mark_sent(notification_id: int) -> None:

    with app_sqlite.get_db_connection() as conn:
        conn.execute("UPDATE notifications SET status = ?, sent_at = ?, last_error = NULL WHERE id = ? AND status = ?", (SENT, now(), notification_id, SENDING))
        conn.commit()



def mark_retry(notification_id: int, attempts: int, delay_seconds: float, error: str) -> None:

    with app_sqlite.get_db_connection() as conn:
        conn.execute("UPDATE notifications SET status = ?, attempts = ?, next_attempt_at = ?, last_error = ? WHERE id = ? AND status = ?",
                     (PENDING, attempts, now(delay_seconds), error, notification_id, SENDING))
        conn.commit()



def mark_failed(notification_id: int, attempts: int, error: str) -> None:

    with app_sqlite.get_db_connection() as conn:
        conn.execute("UPDATE notifications SET status = ?, attempts = ?, last_error = ? WHERE id = ? AND status = ?",
                     (FAILED, attempts, error, notification_id, SENDING))
        conn.commit()



def get(notification_id: int) -> dict|None:

    with app_sqlite.get_db_connection() as conn:
        row = conn.execute("SELECT * FROM notifications WHERE id = ?", (notification_id,)).fetchone()

    return _as_dict(row) if row else None



def get_summary(days: int=30, limit: int=5) -> dict:
    """For the administration (part System): the number of messages which wait, failed in the last days, and the newest failed ones"""

    since = now(-days * 24 * 3600)

    with app_sqlite.get_db_connection() as conn:
        waiting = conn.execute("SELECT count(*) FROM notifications WHERE status IN (?, ?)", (PENDING, SENDING)).fetchone()[0]
        sent = conn.execute("SELECT count(*) FROM notifications WHERE status = ? AND created_at >= ?", (SENT, since)).fetchone()[0]
        failed = conn.execute("SELECT count(*) FROM notifications WHERE status = ? AND created_at >= ?", (FAILED, since)).fetchone()[0]
        last_failed = conn.execute("SELECT id, created_at, event, channel, attempts, last_error FROM notifications WHERE status = ? ORDER BY id DESC LIMIT ?",
                                   (FAILED, limit)).fetchall()

    return {'waiting': waiting, 'sent': sent, 'failed': failed, 'last_failed': [dict(row) for row in last_failed]}



def remove_older_than(days: int) -> int:
    """Sent and failed messages older than `days`"""

    with app_sqlite.get_db_connection() as conn:
        c = conn.execute("DELETE FROM notifications WHERE status IN (?, ?) AND created_at < ?", (SENT, FAILED, now(-days * 24 * 3600)))
        conn.commit()
        return c.rowcount
