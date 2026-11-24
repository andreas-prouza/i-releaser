"""
Data retention: old deployments are removed with their files, optionally archived first (docs/features/data-retention.md).

* Only deployments which are `finished` or `canceled` and haven't changed for C_RETENTION_DAYS (0: keep everything).
* Never the newest finished deployment of a project: it shows what is in production.
* `deploy_versions` stay, so a version number is never given twice.
"""
import datetime
import json
import logging
import os
import shutil
import tarfile
import time

from etc import constants
from modules import files
from modules.db import app_sqlite
from modules.meta_file_status import Meta_file_status


LAST_RUN_FILE = 'retention.last'
RUN_INTERVAL_SECONDS = 24 * 3600

# All steps of a deployment, any depth (as actions_data._STEPS_OF_DEPLOYMENT)
_STEPS = """
    WITH RECURSIVE tree(id) AS (
        SELECT id FROM actions WHERE stage_id IN (SELECT id FROM stages WHERE meta_file_id = :id)
                                  OR deploy_object_id IN (SELECT id FROM deploy_objects WHERE meta_file_id = :id)
        UNION ALL
        SELECT a.id FROM actions a INNER JOIN tree t ON a.action_id = t.id)
"""



def get_candidates(days: int, limit: int|None=None) -> list[dict]:
    """Deployments which are removed: id, project, version, meta_dir, status"""

    if not days:
        return []

    before = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat(sep=' ')

    with app_sqlite.get_db_connection() as conn:
        rows = conn.execute(f"""
            SELECT mf.id, dv.project, dv.version, mf.meta_dir, mf.status FROM meta_files mf
              INNER JOIN deploy_versions dv ON dv.id = mf.deploy_version_id
             WHERE mf.status IN (?, ?) AND mf.update_time < ?
               AND mf.id NOT IN (SELECT max(m2.id) FROM meta_files m2 INNER JOIN deploy_versions d2 ON d2.id = m2.deploy_version_id
                                  WHERE m2.status = ? GROUP BY d2.project)
             ORDER BY mf.id {'LIMIT ' + str(int(limit)) if limit else ''}""",
            (Meta_file_status.FINISHED.value, Meta_file_status.CANCELED.value, before, Meta_file_status.FINISHED.value)).fetchall()

    return [dict(row) for row in rows]



def get_archive_dir() -> str:
    return os.path.join(os.path.dirname(constants.C_APP_DB_FILE), 'archive')



def archive(deployment: dict) -> str:
    """The deployment (as the Web API shows it) and its directory as .tar.gz in var/archive/{project}/"""

    from modules import deploy_version  # noqa: F401 (before meta_file_data, see the import order of the modules)
    from modules.db import meta_file_data

    mf = meta_file_data.get_meta_file_by_id(deployment['id'])
    data = json.dumps(mf.get_all_data_as_dict(), default=str, ensure_ascii=False, indent=2) if mf else '{}'

    directory = os.path.join(get_archive_dir(), str(deployment['project']))
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{deployment['version']}-{deployment['id']}.tar.gz")

    tmp_json = f"{path}.json.tmp"
    with open(tmp_json, 'w', encoding='utf-8') as f:
        f.write(data)

    try:
        with tarfile.open(path, 'w:gz') as tar:
            tar.add(tmp_json, arcname='deployment.json')
            if deployment['meta_dir'] and _is_meta_dir(deployment['meta_dir']) and os.path.isdir(deployment['meta_dir']):
                tar.add(deployment['meta_dir'], arcname='meta')
    finally:
        os.remove(tmp_json)

    return path



def _is_meta_dir(path: str) -> bool:
    """Only a directory below the base of C_META_DIR is removed (never something else of a wrong row)"""

    base = os.path.realpath(constants.C_META_DIR.split('{')[0])
    real = os.path.realpath(path)
    return real != base and real.startswith(base.rstrip(os.sep) + os.sep)



def remove(deployment: dict) -> None:
    """The rows of the deployment in one transaction, then its directory"""

    params = {'id': deployment['id']}

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        c.execute(f"{_STEPS} DELETE FROM action_run_history WHERE action_id IN (SELECT id FROM tree)", params)
        c.execute(f"{_STEPS} DELETE FROM actions WHERE id IN (SELECT id FROM tree)", params)
        for table in ['notifications', 'stage_approvals', 'stages', 'deploy_objects', 'run_history', 'processing_users', 'processing_jobs', 'workflow_definitions']:
            c.execute(f"DELETE FROM {table} WHERE meta_file_id = :id", params)
        c.execute("DELETE FROM meta_files WHERE id = :id", params)
        conn.commit()

    if deployment['meta_dir'] and _is_meta_dir(deployment['meta_dir']) and os.path.isdir(deployment['meta_dir']):
        shutil.rmtree(deployment['meta_dir'], ignore_errors=True)



def run(days: int|None=None, limit: int|None=None) -> dict:
    """
    Removes (and archives, with C_RETENTION_ARCHIVE) the deployments of get_candidates.

    Returns:
        dict: removed (list of 'project version'), archived (paths), errors
    """

    days = constants.C_RETENTION_DAYS if days is None else days
    limit = constants.C_RETENTION_MAX_PER_RUN if limit is None else limit
    result = {'removed': [], 'archived': [], 'errors': []}

    for deployment in get_candidates(days, limit):
        name = f"{deployment['project']} {deployment['version']}"
        try:
            if constants.C_RETENTION_ARCHIVE:
                result['archived'].append(archive(deployment))
            remove(deployment)
            result['removed'].append(name)
        except Exception as e:
            logging.exception(f"Deployment {name} could not be removed: {e}")
            result['errors'].append(f"{name}: {e}")

    if result['removed']:
        logging.info(f"Retention: {len(result['removed'])} deployments older than {days} days removed: {', '.join(result['removed'])}")
        with app_sqlite.get_db_connection() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    return result



def run_if_due() -> dict|None:
    """Once a day, also with several processes of the web app (a lock and the time of the last run)"""

    if not constants.C_RETENTION_DAYS:
        return None

    var_dir = os.path.dirname(constants.C_APP_DB_FILE)
    last_run_file = os.path.join(var_dir, LAST_RUN_FILE)

    with files.lock(os.path.join(var_dir, f"{LAST_RUN_FILE}.lock")):
        if os.path.exists(last_run_file) and time.time() - os.path.getmtime(last_run_file) < RUN_INTERVAL_SECONDS:
            return None
        with open(last_run_file, 'w') as f:
            f.write(datetime.datetime.now().isoformat())

    return run()



def get_sizes() -> dict:
    """Size of the database (MB) and the number of deployments which would be removed now"""

    size = sum(os.path.getsize(f) for f in [constants.C_APP_DB_FILE, f"{constants.C_APP_DB_FILE}-wal"] if os.path.exists(f))
    return {'database_mb': round(size / 1024 / 1024, 1), 'candidates': len(get_candidates(constants.C_RETENTION_DAYS))}
