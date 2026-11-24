"""Start time of the web app and the processing service (docs/features/start-times.md). The pages: test_admin_pages.py"""
import datetime
import os
from unittest.mock import patch

from etc import constants
from modules import processing_service
from modules.db import app_info_data, app_sqlite


UTC = datetime.timezone.utc
PARENT = os.getppid()

# Process ids of other processes: which of them run is decided by the test
SIBLING, ENDED, OTHER_APP, OLD_FORMAT = 900001, 900002, 900003, 900004
RUNNING = {SIBLING, OTHER_APP, OLD_FORMAT, PARENT}


def add_start(data: dict, start: str) -> None:
    with app_sqlite.get_db_connection() as conn:
        conn.execute("INSERT INTO app_info (version, data, start_time) VALUES ('4.1.0', ?, ?)", (str(data), start))


def web_start() -> datetime.datetime|None:
    with patch.object(processing_service, 'is_process_running', lambda pid: pid in RUNNING):
        return app_info_data.get_web_start()



def test_web_start_is_the_oldest_start_of_the_running_processes_of_this_web_app(temp_db):

    # An older process with the id of the sibling: the id has been used again, only the newest start counts
    add_start({'pid': SIBLING, 'ppid': PARENT}, '2020-01-01 07:00:00')
    add_start({'pid': ENDED, 'ppid': PARENT}, '2020-01-01 09:00:00')
    add_start({'pid': OTHER_APP, 'ppid': PARENT + 1}, '2020-01-01 08:00:00')
    # Written by a version before 4.1.0: without the parent, so it can't be told whether it belongs to this web app
    add_start({'pid': OLD_FORMAT, 'thread_id': 1}, '2020-01-01 08:30:00')
    add_start({'pid': SIBLING, 'ppid': PARENT}, '2020-01-01 10:00:00')
    app_info_data.add_app_info()

    assert web_start() == datetime.datetime(2020, 1, 1, 10, 0, tzinfo=UTC)



def test_web_start_is_the_start_of_the_own_process_without_others(temp_db):

    add_start({'pid': ENDED, 'ppid': PARENT}, '2020-01-01 09:00:00')
    before = datetime.datetime.now(UTC).replace(microsecond=0)
    app_info_data.add_app_info()

    start = web_start()
    assert before <= start <= datetime.datetime.now(UTC)



def test_web_start_with_preload_app_is_the_start_of_the_parent(temp_db):
    """gunicorn with preload_app: the master loads the web app once, the workers are its children"""

    add_start({'pid': PARENT, 'ppid': 1}, '2020-01-01 06:00:00')
    app_info_data.add_app_info()

    assert web_start() == datetime.datetime(2020, 1, 1, 6, 0, tzinfo=UTC)



def test_service_start_is_the_time_of_its_pid_file(tmp_path):

    pid_file = tmp_path / 'processing-service.pid'
    pid_file.write_text('4711')
    started = datetime.datetime(2026, 11, 24, 12, 30, 15, tzinfo=UTC)
    os.utime(pid_file, (started.timestamp(), started.timestamp()))

    with patch.object(constants, 'C_SERVICE_PID_FILE', str(pid_file)):
        assert processing_service.get_start() == (started, 4711)

        pid_file.unlink()
        assert processing_service.get_start() is None
