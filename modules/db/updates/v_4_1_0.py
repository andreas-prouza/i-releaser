import logging
import sqlite3

from modules.db import app_sqlite



def add_job_run_at():
    """Scheduled run of a stage (docs/features/scheduled-stage-run.md): the service doesn't take the job before `run_at` (UTC)"""

    logging.info("Adding column run_at to processing_jobs if not exists...")

    with app_sqlite.get_db_connection() as conn:
        try:
            conn.execute("ALTER TABLE processing_jobs ADD COLUMN run_at TEXT")

        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise e
            logging.warning(f"Could not add column run_at: {e}")

        conn.commit()
