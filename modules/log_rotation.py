"""
Rotation of the log files when the web app or the processing service starts (docs/features/data-retention.md).

Not RotatingFileHandler: several processes write the same file (gunicorn workers, job processes), and each of them
would rotate it on its own. At the start one process rotates, under a lock, the others find it rotated.
"""
import fcntl
import os



def rotate_at_start(path: str, max_mb: int, backups: int) -> bool:
    """
    Renames `path` to `path.1` (and `.1` to `.2`, ...) if it's larger than max_mb. Keeps `backups` old files.

    Returns:
        bool: True if it has been rotated
    """

    if not max_mb or not os.path.exists(path) or os.path.getsize(path) <= max_mb * 1024 * 1024:
        return False

    with open(f"{path}.lock", 'a') as lock:
        fcntl.lockf(lock, fcntl.LOCK_EX)
        try:
            # Another process may have rotated it meanwhile
            if not os.path.exists(path) or os.path.getsize(path) <= max_mb * 1024 * 1024:
                return False

            if backups <= 0:
                os.remove(path)
                return True

            oldest = f"{path}.{backups}"
            if os.path.exists(oldest):
                os.remove(oldest)

            for number in range(backups - 1, 0, -1):
                if os.path.exists(f"{path}.{number}"):
                    os.replace(f"{path}.{number}", f"{path}.{number + 1}")

            os.replace(path, f"{path}.1")
            return True
        finally:
            fcntl.lockf(lock, fcntl.LOCK_UN)
