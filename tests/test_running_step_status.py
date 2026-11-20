"""docs/bugfixes/running-step-status-not-stored.md: a step is stored as `in process` while it runs"""
import os, sqlite3, time

import pytest

from web_server import WORKFLOWS, Web_Server


def step(name, cmd, **kw):
    return {'processing_step': name, 'environment': 'PASE', 'execute': cmd, 'check_error': True, **kw}


RUNNING_WORKFLOWS = {
    **WORKFLOWS,
    'running_wf': {
        'name': 'running_wf', 'default_project': 'running',
        'step_action': [step('first', 'echo first'), step('slow', 'sleep 3; echo slow'), step('last', 'echo last')],
        'stages': [
            {'name': 'START', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': ['first', 'slow', 'last']},
            {'name': 'END'},
        ],
    },
    'group_wf': {
        'name': 'group_wf', 'default_project': 'group',
        'step_action': [step('g1', 'sleep 3; echo g1', parallel_group='build', parallel=True),
                        step('g2', 'sleep 3; echo g2', parallel_group='build', parallel=True), step('after', 'echo after')],
        'stages': [
            {'name': 'START', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': ['g1', 'g2', 'after']},
            {'name': 'END'},
        ],
    },
}



@pytest.fixture(scope='module')
def server():
    s = Web_Server(workflows=RUNNING_WORKFLOWS).start()
    yield s
    s.close()


@pytest.fixture()
def boss(server):
    return server.client('boss')


def statuses(client, deployment: int) -> dict:
    return {a['processing_step']: a['status'] for a in client.get_stages(deployment)['START']['actions']}


def wait_for(client, deployment: int, condition, timeout: float=10) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        current = statuses(client, deployment)
        if condition(current):
            return current
        time.sleep(0.1)
    raise AssertionError(f"Not reached: {current}")



def test_running_step_is_in_process(boss):

    deployment = boss.create_deployment('running_wf')
    assert boss.run_stage(deployment, 'START')[0] == 200

    current = wait_for(boss, deployment, lambda s: s['slow'] == 'in process')
    assert current == {'first': 'finished', 'slow': 'in process', 'last': 'new'}

    boss.wait_for_stage(deployment, 'START')
    assert statuses(boss, deployment) == {'first': 'finished', 'slow': 'finished', 'last': 'finished'}



def test_parallel_steps_are_in_process_at_the_same_time(boss):

    deployment = boss.create_deployment('group_wf')
    assert boss.run_stage(deployment, 'START')[0] == 200

    current = wait_for(boss, deployment, lambda s: s['g1'] == 'in process' and s['g2'] == 'in process')
    assert current['after'] == 'new'

    # The deployment page says which steps run
    _, _, page = boss.get(f"/show_details/{deployment}", headers={'Accept': 'text/html'})
    assert 'is running: steps 1 and 2 of 3 at the same time.' in page
    assert page.count('data-status="in process"') >= 2

    boss.wait_for_stage(deployment, 'START')



def test_step_left_in_process_runs_again_with_continue(server, boss):
    """A crash while a step ran leaves it `in process`: Continue runs it again"""

    deployment = boss.create_deployment('running_wf')
    first = [a for a in boss.get_stages(deployment)['START']['actions'] if a['processing_step'] == 'first'][0]

    db = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'), timeout=10)
    db.execute("UPDATE actions SET status = 'in process' WHERE id = ?", (first['id'],))
    db.commit()
    db.close()
    assert statuses(boss, deployment)['first'] == 'in process'

    assert boss.run_stage(deployment, 'START', 'continue')[0] == 200
    boss.wait_for_stage(deployment, 'START')

    actions = {a['processing_step']: a for a in boss.get_stages(deployment)['START']['actions']}
    assert actions['first']['status'] == 'finished'
    assert len(actions['first']['run_history']) == 1
