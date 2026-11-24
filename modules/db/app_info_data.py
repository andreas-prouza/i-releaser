import ast
import datetime
import os
import threading
from modules.db import app_sqlite
from modules import version


# Starts of web app processes which are looked at for the start of the web app: the workers of several restarts
RECENT_STARTS = 200



def add_app_info():

    data: dict = {
        'pid': os.getpid(),
        # The gunicorn master: the workers of one web app have the same parent (docs/features/start-times.md)
        'ppid': os.getppid(),
        'thread_id': threading.get_ident(),
        'native_thread_id': threading.get_native_id()
    }

    with app_sqlite.get_db_connection() as conn:

        c = conn.cursor()
        c.execute('''
            INSERT INTO app_info (version, data)
            VALUES (?, ?)
        ''', (
            version.APP_VERSION,
            str(data),
        ))

        app_info_id = c.lastrowid

        if app_info_id is None:
            raise Exception("Failed to insert app info.")



def get_app_info() -> dict | None:
    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM app_info ORDER BY id DESC LIMIT 1')
        row = c.fetchone()
        if row:
            return {
                'id': row[0],
                'version': row[1],
                'data': row[2],
                'created_at': row[3]
            }
        else:
            return None



def get_web_start() -> datetime.datetime | None:
    """
    Start of the web app (docs/features/start-times.md), in UTC: the oldest start of its processes which still run.

    gunicorn starts several workers, each of them writes its start. Those of this web app have the same parent
    (the gunicorn master), or are that parent (gunicorn with `preload_app`). A process id can be used again
    (e.g. after a restart of the system): only the newest start of each process id counts.
    """

    from modules.processing_service import is_process_running

    own, parent = os.getpid(), os.getppid()
    seen: set[int] = set()
    starts: list[datetime.datetime] = []

    with app_sqlite.get_db_connection() as conn:
        rows = conn.execute('SELECT data, start_time FROM app_info ORDER BY id DESC LIMIT ?', (RECENT_STARTS,)).fetchall()

    for row in rows:

        try:
            data = ast.literal_eval(row['data'])
            pid = data['pid']
            start = datetime.datetime.fromisoformat(row['start_time'])
        except (ValueError, SyntaxError, KeyError, TypeError):
            continue

        if pid in seen:
            continue
        seen.add(pid)

        if pid not in (own, parent) and data.get('ppid') != parent:
            continue

        if pid == own or is_process_running(pid):
            # CURRENT_TIMESTAMP of SQLite is UTC
            starts.append(start.replace(tzinfo=datetime.timezone.utc))

    return min(starts, default=None)
