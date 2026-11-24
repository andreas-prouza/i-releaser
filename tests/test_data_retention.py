"""Data retention: old deployments and log files (docs/features/data-retention.md)"""
import json, os, sqlite3, tarfile

import pytest

from web_server import Web_Server

from modules import log_rotation


@pytest.fixture()
def server():
    s = Web_Server(settings="C_RETENTION_DAYS = 30\nC_RETENTION_ARCHIVE = True\n").start()
    yield s
    s.close()


def db(server):
    conn = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'))
    conn.row_factory = sqlite3.Row
    return conn


def make_old(server, deployment: int) -> None:
    with db(server) as conn:
        conn.execute("UPDATE meta_files SET update_time = '2020-01-01 10:00:00' WHERE id = ?", (deployment,))


def finished_deployment(client) -> int:
    deployment = client.create_deployment('seq_wf')
    client.finish_deployment(deployment)
    return deployment


def test_old_deployments_are_removed(server):

    boss = server.client('boss')

    old_finished = finished_deployment(boss)
    newest_finished = finished_deployment(boss)
    canceled = boss.create_deployment('seq_wf')
    boss.post(f"/api/cancel_deployment/{canceled}")
    open_one = boss.create_deployment('seq_wf')

    for deployment in [old_finished, newest_finished, canceled, open_one]:
        make_old(server, deployment)

    with db(server) as conn:
        meta_dir = conn.execute("SELECT meta_dir FROM meta_files WHERE id = ?", (old_finished,)).fetchone()['meta_dir']
    assert os.path.isdir(meta_dir)

    _, _, page = boss.get('/settings', headers={'Accept': 'text/html'})
    assert 'data-action="run-retention"' in page

    status, result = boss.post_json('/api/retention/run')
    assert status == 200, result
    assert len(result['removed']) == 2

    with db(server) as conn:
        remaining = {row['id'] for row in conn.execute("SELECT id FROM meta_files")}
        # The newest finished deployment of the project and the one which isn't finished stay
        assert {newest_finished, open_one} <= remaining
        assert old_finished not in remaining and canceled not in remaining

        # No rows of the removed deployments are left
        for table in ['stages', 'deploy_objects', 'run_history', 'processing_users', 'processing_jobs', 'workflow_definitions']:
            assert conn.execute(f"SELECT count(*) FROM {table} WHERE meta_file_id NOT IN (SELECT id FROM meta_files)").fetchone()[0] == 0, table
        assert conn.execute("SELECT count(*) FROM actions WHERE stage_id IS NOT NULL AND stage_id NOT IN (SELECT id FROM stages)").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM action_run_history WHERE action_id NOT IN (SELECT id FROM actions)").fetchone()[0] == 0

        # The version numbers stay
        assert conn.execute("SELECT count(*) FROM deploy_versions").fetchone()[0] == 4

    assert not os.path.exists(meta_dir)

    archive = os.path.join(server.directory, 'var', 'archive', 'seq')
    names = sorted(os.listdir(archive))
    assert len(names) == 2
    with tarfile.open(os.path.join(archive, names[0])) as tar:
        data = json.load(tar.extractfile('deployment.json'))
        assert data['general']['id'] in [old_finished, canceled]


def test_only_admins_remove(server):
    assert server.client('runner').post('/api/retention/run')[0] == 403


def test_nothing_is_removed_without_the_setting():

    server = Web_Server().start()
    try:
        assert server.client('boss').post('/api/retention/run')[0] == 409
    finally:
        server.close()


def test_log_rotation(tmp_path):

    log = tmp_path / 'index.log'
    log.write_text('x' * (2 * 1024 * 1024))

    assert log_rotation.rotate_at_start(str(log), max_mb=1, backups=2)
    assert not log.exists() and (tmp_path / 'index.log.1').exists()

    log.write_text('y' * (2 * 1024 * 1024))
    assert log_rotation.rotate_at_start(str(log), max_mb=1, backups=2)
    log.write_text('z' * (2 * 1024 * 1024))
    assert log_rotation.rotate_at_start(str(log), max_mb=1, backups=2)

    assert (tmp_path / 'index.log.1').read_text()[0] == 'z'
    assert (tmp_path / 'index.log.2').read_text()[0] == 'y'
    assert not (tmp_path / 'index.log.3').exists()

    log.write_text('small')
    assert not log_rotation.rotate_at_start(str(log), max_mb=1, backups=2)
