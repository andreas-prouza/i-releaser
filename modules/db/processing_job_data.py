import datetime
import logging
import sqlite3
import time

from modules.db import app_sqlite
from modules import processing_job
from modules.job_status import Status as Job_Status


ACTIVE_STATUS = [Job_Status.QUEUED, Job_Status.RUNNING]



def _convert_row_to_object(row: sqlite3.Row) -> processing_job.Processing_Job:
    return processing_job.Processing_Job(**dict(row))



def create_job(meta_file_id: int, stage_id: int, processing_step: str|None=None, continue_run: bool=True, user: str|None=None) -> processing_job.Processing_Job:
    """Creates a new Processing_Job instance and adds it to the queue of the processing service."""

    job = processing_job.Processing_Job(meta_file_id=meta_file_id, stage_id=stage_id, processing_step=processing_step, continue_run=continue_run, user=user)

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()

        c.execute('''
            INSERT INTO processing_jobs (meta_file_id, stage_id, processing_step, continue_run, user, status, create_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            job.meta_file_id, job.stage_id, job.processing_step, job.continue_run, job.user,
            job.status.value, job.create_time.isoformat()
        ))
        job.id = c.lastrowid

        conn.commit()
    logging.info(f"Processing job {job.id} for stage ID {stage_id} of meta file ID {meta_file_id} added to queue.")

    return job



def get_job(job_id: int) -> processing_job.Processing_Job|None:

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM processing_jobs WHERE id = ?", (job_id,))
        row = c.fetchone()

    return _convert_row_to_object(row) if row else None



def get_jobs(status: list[Job_Status]|None=None, meta_file_id: int|None=None, limit: int|None=None) -> list[processing_job.Processing_Job]:
    """
    Args:
        limit (int, optional): Only the newest jobs
    Returns:
        Jobs in the order they have been created
    """

    sql = "SELECT * FROM processing_jobs WHERE 1=1"
    param = []

    if status is not None:
        sql += f" AND status in ({', '.join('?' * len(status))})"
        param += [s.value for s in status]

    if meta_file_id is not None:
        sql += " AND meta_file_id = ?"
        param.append(meta_file_id)

    sql += " ORDER BY id DESC"

    if limit is not None:
        sql += " LIMIT ?"
        param.append(limit)

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        c.execute(sql, param)
        rows = c.fetchall()

    return [_convert_row_to_object(row) for row in reversed(rows)]



def get_active_jobs(meta_file_id: int|None=None) -> list[processing_job.Processing_Job]:
    """Jobs which are waiting for the processing service or are processed right now"""

    return get_jobs(status=ACTIVE_STATUS, meta_file_id=meta_file_id)



def claim_next_job() -> processing_job.Processing_Job|None:
    """
    Takes the oldest job from the queue and sets it to status `running`.
    A job is only handed out once, even if multiple processes ask for it.
    """

    now = datetime.datetime.now().isoformat()

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()

        while True:
            c.execute("SELECT id FROM processing_jobs WHERE status = ? ORDER BY id LIMIT 1", (Job_Status.QUEUED.value,))
            row = c.fetchone()

            if not row:
                return None

            c.execute("UPDATE processing_jobs SET status = ?, start_time = ?, heartbeat = ? WHERE id = ? AND status = ?",
                      (Job_Status.RUNNING.value, now, time.time(), row['id'], Job_Status.QUEUED.value))
            conn.commit()

            # Otherwise it has been claimed or canceled meanwhile
            if c.rowcount == 1:
                break

    logging.info(f"Processing job {row['id']} claimed.")
    return get_job(row['id'])



def set_job_pid(job_id: int, pid: int) -> None:

    with app_sqlite.get_db_connection() as conn:
        conn.execute("UPDATE processing_jobs SET pid = ?, heartbeat = ? WHERE id = ?", (pid, time.time(), job_id))
        conn.commit()



def touch_heartbeat(job_id: int) -> None:

    with app_sqlite.get_db_connection() as conn:
        conn.execute("UPDATE processing_jobs SET heartbeat = ? WHERE id = ?", (time.time(), job_id))
        conn.commit()



def finish_job(job_id: int, status: Job_Status, error: str|None=None) -> None:
    """Sets the final status of a job"""

    with app_sqlite.get_db_connection() as conn:
        conn.execute("UPDATE processing_jobs SET status = ?, error = ?, end_time = ? WHERE id = ?",
                     (status.value, error, datetime.datetime.now().isoformat(), job_id))
        conn.commit()
    logging.info(f"Processing job {job_id} ended with status '{status.value}'.")



def cancel_job(job_id: int) -> bool:
    """
    Removes a job from the queue.

    Returns:
        bool: False if the job is not in the queue anymore (e.g. because it's already running)
    """

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE processing_jobs SET status = ?, end_time = ? WHERE id = ? AND status = ?",
                  (Job_Status.CANCELED.value, datetime.datetime.now().isoformat(), job_id, Job_Status.QUEUED.value))
        conn.commit()

    return c.rowcount == 1



def cancel_queued_jobs(meta_file_id: int) -> int:
    """
    Removes all jobs of a deployment from the queue. Running jobs are not affected.

    Returns:
        int: Number of canceled jobs
    """

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE processing_jobs SET status = ?, end_time = ? WHERE meta_file_id = ? AND status = ?",
                  (Job_Status.CANCELED.value, datetime.datetime.now().isoformat(), meta_file_id, Job_Status.QUEUED.value))
        conn.commit()

    return c.rowcount
