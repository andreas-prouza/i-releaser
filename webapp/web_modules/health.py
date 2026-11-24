"""
Health check for monitoring tools and the reverse proxy: GET /healthz (docs/features/health-check.md).

Without login only `ok`/`error` per check; with a login or an API token also the version and the details.
"""
import logging
import os
import shutil

from etc import constants
from modules import processing_service, processing_settings, version
from modules.db import app_sqlite



def check_database() -> str|None:
    """None if it's ok, otherwise the reason"""

    try:
        with app_sqlite.get_db_connection(timeout=5) as conn:
            conn.execute("SELECT 1").fetchone()
        if app_sqlite.get_schema_version() < app_sqlite.SCHEMA_VERSION:
            return f"Database has version {app_sqlite.get_schema_version()}, {app_sqlite.SCHEMA_VERSION} is needed"
    except Exception as e:
        return f"{type(e).__name__}: {e}"

    return None



def check_processing_service() -> str|None:
    """Only in the processing mode `service`: no stage can run without it"""

    try:
        if processing_settings.get_processing_mode() != 'service':
            return None
        return None if processing_service.notify() else "The processing service is not running"
    except Exception as e:
        return f"{type(e).__name__}: {e}"



def check_disk_space() -> str|None:

    minimum = constants.C_HEALTH_MIN_FREE_MB * 1024 * 1024
    directories = {os.path.dirname(constants.C_APP_DB_FILE), constants.C_META_DIR.split('{')[0]}

    for directory in sorted(directories):
        if not os.path.isdir(directory):
            continue
        free = shutil.disk_usage(directory).free
        if free < minimum:
            return f"Only {free // (1024 * 1024)} MB free in {directory} (C_HEALTH_MIN_FREE_MB = {constants.C_HEALTH_MIN_FREE_MB})"

    return None



CHECKS = {
    'database': check_database,
    'processing_service': check_processing_service,
    'disk_space': check_disk_space,
}



def get_health(details: bool) -> tuple[int, dict]:
    """
    Returns:
        (HTTP status, answer): 200 if all checks are ok, 503 otherwise
    """

    results = {name: check() for name, check in CHECKS.items()}
    ok = all(result is None for result in results.values())

    for name, result in results.items():
        if result is not None:
            logging.warning(f"Health check {name}: {result}")

    answer = {'status': 'ok' if ok else 'error', 'checks': {name: 'ok' if result is None else 'error' for name, result in results.items()}}

    if details:
        answer['version'] = version.APP_VERSION
        answer['details'] = {name: result for name, result in results.items() if result is not None}

    return (200 if ok else 503), answer
