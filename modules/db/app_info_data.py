import os
import threading
from modules.db import app_sqlite
from etc import constants




def add_app_info():

    data: dict = {
        'pid': os.getpid(),
        'thread_id': threading.get_ident(),
        'native_thread_id': threading.get_native_id()
    }

    with app_sqlite.get_db_connection() as conn:

        c = conn.cursor()
        c.execute('''
            INSERT INTO app_info (version, data) 
            VALUES (?, ?)
        ''', (
            constants.C_APP_VERSION,
            str(data),
        ))

        app_info_id = c.lastrowid

        if app_info_id is None:
            raise Exception("Failed to insert app info.")


