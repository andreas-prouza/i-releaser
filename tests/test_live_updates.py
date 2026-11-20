"""docs/features/web-ui-live-updates.md: the signature of /api/watch_state has a hash per part of the deployment page"""
import http.client, json, os, sqlite3

import pytest

from web_server import WORKFLOWS, Web_Server


@pytest.fixture(scope='module')
def server():
    s = Web_Server(workflows=WORKFLOWS).start()
    yield s
    s.close()


@pytest.fixture()
def boss(server):
    return server.client('boss')


class Watch:
    """The stream of /api/watch_state: the first message, then the next ones"""

    def __init__(self, server, client, deployment: int):
        self.connection = http.client.HTTPConnection('127.0.0.1', server.port, timeout=15)
        self.connection.request('GET', f"/api/watch_state/{deployment}", headers={'Cookie': f"session_id={client.session_id}"})
        self.response = self.connection.getresponse()

    def next(self) -> dict:
        for _ in range(30):
            line = self.response.readline()
            if line.startswith(b'data: '):
                return json.loads(line[len(b'data: '):])
        raise AssertionError('No message')

    def close(self):
        self.connection.close()


def changed(before: dict, after: dict) -> set:
    names = {name for name in after['parts'] if before['parts'][name] != after['parts'][name]}
    if before['page'] != after['page']:
        names.add('page')
    if before['stages'] != after['stages']:
        names.add('stages')
    return names


def add_object(server, deployment: int) -> int:
    db = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'), timeout=10)
    cursor = db.execute("""INSERT INTO deploy_objects (meta_file_id, level, prod_lib, lib, name, type, attribute, deploy_status, ready, properties)
                           VALUES (?, 1, 'prodlib', 'devlib', 'orders', 'file', 'pf', 'new', 1, '{}')""", (deployment,))
    db.commit()
    db.close()
    return cursor.lastrowid



def test_signature_has_the_parts_of_the_page(server, boss):

    deployment = boss.create_deployment('seq_wf', {'ticket': 'T-1'})
    add_object(server, deployment)
    watch = Watch(server, boss, deployment)

    try:
        first = watch.next()
        assert set(first) == {'page', 'stages', 'parts'}
        assert set(first['parts']) == {'header', 'flow', 'objects', 'activity'}

        # An object is excluded: only `objects` (and the activity: an entry in the processing history)
        assert boss.post(f"/api/set_source_ready_4_deployment/{deployment}", {'lib': 'devlib', 'name': 'orders', 'type': 'file', 'checked': False})[0] == 200
        second = watch.next()
        assert {'objects', 'activity'} <= changed(first, second) <= {'objects', 'activity', 'header'}
        assert 'flow' not in changed(first, second) and 'stages' not in changed(first, second)

        # A stage runs: the flow, the stages and the activity
        assert boss.run_stage(deployment, 'START')[0] == 200
        boss.wait_for_stage(deployment, 'START')
        latest = second
        names = set()
        for _ in range(6):
            current = watch.next()
            names |= changed(latest, current)
            latest = current
            if boss.get_stages(deployment)['PROD']['status'] == 'ready' and {'flow', 'stages', 'activity'} <= names:
                break
        assert {'flow', 'stages', 'page', 'activity'} <= names
        assert latest['parts']['objects'] == second['parts']['objects']
    finally:
        watch.close()
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_page_and_stages_stay_for_other_clients(server, boss):
    """The OBI extension uses `page` and `stages`: an object which is excluded doesn't change them"""

    deployment = boss.create_deployment('seq_wf', {'ticket': 'T-1'})
    add_object(server, deployment)
    watch = Watch(server, boss, deployment)

    try:
        first = watch.next()
        boss.post(f"/api/set_source_ready_4_deployment/{deployment}", {'lib': 'devlib', 'name': 'orders', 'type': 'file', 'checked': False})
        second = watch.next()
        assert second['page'] == first['page'] and second['stages'] == first['stages']

        # Custom data: the header
        assert boss.post(f"/api/edit_custom_data/{deployment}", {'fields': {'$.ticket': 'T-2'}})[0] == 200
        third = watch.next()
        assert 'header' in changed(second, third)
        assert third['page'] == second['page']
    finally:
        watch.close()
        boss.post(f"/api/cancel_deployment/{deployment}")



def test_a_starting_step_changes_the_marker(server, boss):
    """A step which starts only changes its own row: the marker counts the running steps"""

    deployment = boss.create_deployment('seq_wf', {'ticket': 'T-1'})
    db = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'), timeout=10)
    watch = Watch(server, boss, deployment)

    try:
        first = watch.next()
        step_id = boss.get_stages(deployment)['START']['actions'][0]['id']
        db.execute("UPDATE actions SET status = 'in process' WHERE id = ?", (step_id,))
        db.commit()

        second = watch.next()
        assert 'stages' in changed(first, second)
    finally:
        db.close()
        watch.close()
        boss.post(f"/api/cancel_deployment/{deployment}")
