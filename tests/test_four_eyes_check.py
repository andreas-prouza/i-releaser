"""Four-eyes check (docs/features/four-eyes-check.md)"""
import copy, json, os, sqlite3

import pytest

from web_server import USERS, WORKFLOWS, Web_Server


EYES_WF = {
    'name': 'eyes_wf',
    'default_project': 'eyes',
    'editable_fields': ['$.ticket'],
    'step_action': [{'processing_step': 'quick', 'environment': 'PASE', 'execute': 'echo quick', 'check_error': True}],
    'stages': [
        {'name': 'START', 'next_stages': ['PROD'], 'host': 'localhost', 'processing_steps': ['quick']},
        {'name': 'PROD', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': ['quick'], 'four_eyes_check': True},
        {'name': 'END'},
    ],
}

TEAM = {
    **copy.deepcopy(USERS),
    # Creates the deployments
    'creator': {'permissions': {'general': ['read', 'start workflow', 'run', 'edit-custom-data'], 'workflows': {}}},
    'checker': {'permissions': {'general': ['read', 'run'], 'workflows': {'eyes_wf': {'general': [], 'stages': {'PROD': ['4-eyes check']}}}}},
    'checker2': {'permissions': {'general': ['read', 'run', '4-eyes check'], 'workflows': {}}},
    # Creates deployments and may approve
    'lead': {'permissions': {'general': ['read', 'start workflow', 'run', '4-eyes check'], 'workflows': {}}},
}


@pytest.fixture(scope='module')
def server():
    s = Web_Server(workflows={**WORKFLOWS, 'eyes_wf': EYES_WF}, users=TEAM).start()
    yield s
    s.close()


def ready_for_prod(server) -> tuple:
    creator = server.client('creator')
    # Each deployment of its own project: they don't wait for each other
    deployment = creator.create_deployment('eyes_wf')
    assert creator.run_stage(deployment, 'START')[0] == 200
    creator.wait_for_stage(deployment, 'START')
    return creator, deployment


def history(server, deployment: int) -> list[str]:
    with sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite')) as conn:
        return [row[0] for row in conn.execute("SELECT action FROM processing_users WHERE meta_file_id = ? ORDER BY id", (deployment,))]


def approve(client, deployment: int) -> tuple:
    return client.post_json(f"/api/approve_stage/{deployment}/{client.get_stages(deployment)['PROD']['id']}")


def finish_all(server):
    boss = server.client('boss')
    for d in json.loads(boss.get('/api/list_deployments/eyes')[2]):
        if d['status'] not in ['finished', 'canceled']:
            boss.post(f"/api/cancel_deployment/{d['meta_file_id']}")


def test_stage_runs_only_after_an_approval(server):

    finish_all(server)
    creator, deployment = ready_for_prod(server)

    status, body = creator.run_stage(deployment, 'PROD')
    assert status == 409 and 'approval' in body['message']

    # The one who created it can't approve it
    status, body = approve(creator, deployment)
    assert status == 403 or 'created this deployment' in body['message']

    checker = server.client('checker')
    status, body = approve(checker, deployment)
    assert status == 200, body
    assert 'approve_stage' in history(server, deployment)

    # The one who approved it can't run it
    status, body = checker.run_stage(deployment, 'PROD')
    assert status == 409 and 'another person' in body['message']

    assert creator.run_stage(deployment, 'PROD')[0] == 200
    assert creator.wait_for_stage(deployment, 'PROD')['status'] == 'finished'


def test_change_after_the_approval_needs_a_new_one(server):

    finish_all(server)
    creator, deployment = ready_for_prod(server)
    assert approve(server.client('checker'), deployment)[0] == 200

    assert creator.post_json(f"/api/edit_custom_data/{deployment}", {'fields': {'$.ticket': 'ABC-1'}})[0] == 200
    assert 'approval_invalid' in history(server, deployment)

    status, body = creator.run_stage(deployment, 'PROD')
    assert status == 409 and 'changed' in body['message']

    assert approve(server.client('checker2'), deployment)[0] == 200
    assert creator.run_stage(deployment, 'PROD')[0] == 200


def test_permission_for_the_stage(server):

    finish_all(server)
    _, deployment = ready_for_prod(server)

    assert approve(server.client('runner'), deployment)[0] == 403


def test_page_shows_the_approval(server):

    finish_all(server)
    creator, deployment = ready_for_prod(server)
    prod = creator.get_stages(deployment)['PROD']['id']

    _, _, page = server.client('checker').get(f"/show_details/{deployment}", headers={'Accept': 'text/html'})
    assert 'needs the approval of a second person' in page
    assert 'data-action="approve-stage"' in page

    _, _, steps = server.client('checker').get(f"/show_details/{deployment}/stage/{prod}", headers={'Accept': 'text/html'})
    assert 'Needed (four-eyes check)' in steps

    approve(server.client('checker'), deployment)
    _, _, steps = creator.get(f"/show_details/{deployment}/stage/{prod}", headers={'Accept': 'text/html'})
    assert 'Approved by checker' in steps


def test_scheduled_run_needs_the_approval():

    server = Web_Server(workflows={**WORKFLOWS, 'eyes_wf': EYES_WF}, users=TEAM, settings="C_PROCESSING_MODE = 'service'\n").start()
    try:
        creator, deployment = None, None
        creator = server.client('creator')
        deployment = creator.create_deployment('eyes_wf')
        # START runs in the processing service, which isn't running: set it finished like a run would
        with sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite')) as conn:
            conn.execute("UPDATE stages SET status = 'finished' WHERE meta_file_id = ? AND name = 'START'", (deployment,))
            conn.execute("UPDATE stages SET status = 'ready' WHERE meta_file_id = ? AND name = 'PROD'", (deployment,))
        prod = creator.get_stages(deployment)['PROD']['id']

        status, body = creator.post_json(f"/api/run_stage/{deployment}/{prod}/continue", {'run_at': '2099-01-01T10:00:00+00:00'})
        assert status == 409 and 'approval' in body['message']
    finally:
        server.close()


def test_creator_can_not_approve(server):

    finish_all(server)
    lead = server.client('lead')
    deployment = lead.create_deployment('eyes_wf')

    status, body = approve(lead, deployment)
    assert status == 409 and 'created this deployment' in body['message']
