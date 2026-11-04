"""Running deployments through the web app, tested against the running application"""
import json, os, threading, time
from concurrent.futures import ThreadPoolExecutor

import pytest

from web_server import Web_Server


@pytest.fixture(scope='module')
def server():
    s = Web_Server().start()
    yield s
    s.close()


@pytest.fixture()
def boss(server):
    return server.client('boss')


def cancel_open_deployments(client, project: str) -> None:
    """Deployments of a project run one after the other"""

    for deployment in json.loads(client.get(f"/api/list_deployments/{project}")[2]):
        if deployment['status'] not in ['finished', 'canceled']:
            client.post(f"/api/cancel_deployment/{deployment['meta_file_id']}")



#---------------------------------------------------------
# parallel-stages-lost-update
#---------------------------------------------------------

def run_parallel_stages(client, deployment: int) -> None:

    assert client.run_stage(deployment, 'START')[0] == 200
    client.wait_for_stage(deployment, 'START')

    stages = client.get_stages(deployment)

    assert client.post_json(f"/api/run_stage/{deployment}/{stages['A']['id']}/continue")[0] == 200
    time.sleep(0.5)
    assert client.post_json(f"/api/run_stage/{deployment}/{stages['B']['id']}/continue")[0] == 200

    client.wait_for_stage(deployment, 'A')
    client.wait_for_stage(deployment, 'B')



@pytest.mark.parametrize('run', range(3))
def test_parallel_stages_keep_their_progress(server, boss, run):

    deployment = boss.create_deployment('par_wf')
    run_parallel_stages(boss, deployment)

    time.sleep(0.5)
    stages = boss.get_stages(deployment)

    for name in ['A', 'B']:
        assert stages[name]['status'] == 'finished'
        assert {action['status'] for action in stages[name]['actions']} == {'finished'}

    assert stages['END']['status'] == 'ready'
    assert boss.get_deployment(deployment)['general']['status'] == 'ready'

    assert boss.run_stage(deployment, 'END')[0] == 200
    boss.wait_for_stage(deployment, 'END')
    time.sleep(0.3)
    assert boss.get_deployment(deployment)['general']['status'] == 'finished'



def test_deployment_stays_in_process_while_another_stage_runs(boss):

    deployment = boss.create_deployment('par_wf')
    assert boss.run_stage(deployment, 'START')[0] == 200
    boss.wait_for_stage(deployment, 'START')

    stages = boss.get_stages(deployment)

    # A takes 2 seconds, B 2 seconds: start them shifted, so one ends first
    boss.post_json(f"/api/run_stage/{deployment}/{stages['B']['id']}/continue")
    time.sleep(1)
    boss.post_json(f"/api/run_stage/{deployment}/{stages['A']['id']}/continue")

    boss.wait_for_stage(deployment, 'B')
    assert boss.get_stages(deployment)['A']['status'] == 'in process'
    assert boss.get_deployment(deployment)['general']['status'] == 'in process'

    boss.wait_for_stage(deployment, 'A')



def test_custom_data_edited_while_a_stage_runs_is_kept(boss):

    deployment = boss.create_deployment('par_wf', {'ticket': 'OLD'})
    boss.run_stage(deployment, 'START')
    boss.wait_for_stage(deployment, 'START')

    assert boss.run_stage(deployment, 'A')[0] == 200
    time.sleep(0.3)

    assert boss.post_json(f"/api/edit_custom_data/{deployment}", {'fields': {'$.ticket': 'NEW'}})[0] == 200

    boss.wait_for_stage(deployment, 'A')

    assert boss.get_deployment(deployment)['custom_data'] == {'ticket': 'NEW'}



def test_error_check_changed_while_a_stage_runs_is_kept(boss):

    deployment = boss.create_deployment('par_wf')
    boss.run_stage(deployment, 'START')
    boss.wait_for_stage(deployment, 'START')

    stages = boss.get_stages(deployment)
    assert boss.run_stage(deployment, 'A')[0] == 200
    time.sleep(0.2)

    # The second step of the stage hasn't been run yet
    action = stages['A']['actions'][1]
    assert boss.post(f"/api/set_check_error/{deployment}/{stages['A']['id']}/{action['id']}/false")[0] == 200

    boss.wait_for_stage(deployment, 'A')

    assert boss.get_stages(deployment)['A']['actions'][1]['check_error'] in [False, 0]



def test_deployment_canceled_while_a_stage_runs_stays_canceled(boss):

    deployment = boss.create_deployment('par_wf')
    boss.run_stage(deployment, 'START')
    boss.wait_for_stage(deployment, 'START')

    boss.run_stage(deployment, 'A')
    time.sleep(0.2)
    assert boss.post(f"/api/cancel_deployment/{deployment}")[0] == 200

    boss.wait_for_stage(deployment, 'A')
    time.sleep(0.3)

    assert boss.get_deployment(deployment)['general']['status'] == 'canceled'



#---------------------------------------------------------
# rerun-finished-stage-blocks-project
#---------------------------------------------------------

def test_finished_stage_can_not_be_run_again(boss):

    cancel_open_deployments(boss, 'seq')

    deployment = boss.create_deployment('seq_wf')
    assert boss.run_stage(deployment, 'START')[0] == 200
    boss.wait_for_stage(deployment, 'START')

    status, data = boss.run_stage(deployment, 'START')

    assert status == 409
    assert data['status'] == 'error'
    time.sleep(0.2)
    assert boss.get_deployment(deployment)['general']['status'] == 'ready'



def test_finished_deployment_stays_finished_and_blocks_nothing(boss):

    cancel_open_deployments(boss, 'seq')

    deployment = boss.create_deployment('seq_wf')
    boss.finish_deployment(deployment)
    assert boss.get_deployment(deployment)['general']['status'] == 'finished'

    assert boss.run_stage(deployment, 'PROD')[0] == 409
    time.sleep(0.2)
    assert boss.get_deployment(deployment)['general']['status'] == 'finished'

    next_deployment = boss.create_deployment('seq_wf')
    assert boss.run_stage(next_deployment, 'START')[0] == 200
    boss.wait_for_stage(next_deployment, 'START')



def test_double_click_runs_a_stage_once(server, boss):

    deployment = boss.create_deployment('slow_wf')
    start_id = boss.get_stages(deployment)['START']['id']

    def run(_):
        return server.client('boss').post_json(f"/api/run_stage/{deployment}/{start_id}/continue")[0]

    with ThreadPoolExecutor(5) as pool:
        results = list(pool.map(run, range(5)))

    assert sorted(results).count(200) == 1
    assert set(results) == {200, 409}

    stage = boss.wait_for_stage(deployment, 'START')
    assert len(stage['actions'][0]['run_history']) == 1

    boss.post(f"/api/cancel_deployment/{deployment}")



def test_only_one_stage_at_a_time_without_parallel_execution(boss):

    deployment = boss.create_deployment('slow_wf')
    assert boss.run_stage(deployment, 'START')[0] == 200
    boss.wait_for_stage(deployment, 'START')

    stages = boss.get_stages(deployment)

    assert boss.post_json(f"/api/run_stage/{deployment}/{stages['A']['id']}/continue")[0] == 200
    assert boss.post_json(f"/api/run_stage/{deployment}/{stages['B']['id']}/continue")[0] == 409

    boss.wait_for_stage(deployment, 'A')
    boss.post(f"/api/cancel_deployment/{deployment}")



def test_unknown_stage_and_deployment(boss):

    deployment = boss.create_deployment('hidden_wf')

    assert boss.post(f"/api/run_stage/{deployment}/999999/continue")[0] == 404
    assert boss.post("/api/run_stage/999999/1/continue")[0] == 404

    boss.post(f"/api/cancel_deployment/{deployment}")



def test_invalid_run_option(boss):

    deployment = boss.create_deployment('hidden_wf')
    start_id = boss.get_stages(deployment)['START']['id']

    assert boss.post(f"/api/run_stage/{deployment}/{start_id}/whatever")[0] == 422

    boss.post(f"/api/cancel_deployment/{deployment}")



def test_stuck_deployment_can_be_corrected(server, boss):

    cancel_open_deployments(boss, 'seq')

    deployment = boss.create_deployment('seq_wf')
    boss.finish_deployment(deployment)

    # Left behind by the bug of older versions
    import sqlite3
    db = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'), timeout=10)
    db.execute("UPDATE meta_files SET status = 'in process' WHERE id = ?", (deployment,))
    db.commit()
    db.close()

    assert boss.post(f"/api/reset_deployment_status/{deployment}")[0] == 200
    assert boss.get_deployment(deployment)['general']['status'] == 'finished'



#---------------------------------------------------------
# reset-ignores-running-jobs
#---------------------------------------------------------

def test_stage_which_just_changed_can_not_be_reset(boss):

    deployment = boss.create_deployment('slow_wf')
    assert boss.run_stage(deployment, 'START')[0] == 200
    start_id = boss.get_stages(deployment)['START']['id']

    status, data = boss.post_json(f"/api/reset_stage_status/{deployment}/{start_id}")
    assert status == 409
    assert 'may still be running' in data['message']

    assert boss.post(f"/api/reset_deployment_status/{deployment}")[0] == 409

    boss.wait_for_stage(deployment, 'START')
    boss.post(f"/api/cancel_deployment/{deployment}")



def test_hanging_stage_can_be_reset(server, boss):

    deployment = boss.create_deployment('slow_wf')
    start_id = boss.get_stages(deployment)['START']['id']

    import sqlite3
    db = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'), timeout=10)
    db.execute("UPDATE stages SET status = 'in process', update_time = '2020-01-01 00:00:00' WHERE id = ?", (start_id,))
    db.execute("UPDATE meta_files SET status = 'in process' WHERE id = ?", (deployment,))
    db.commit()
    db.close()

    assert boss.post(f"/api/reset_stage_status/{deployment}/{start_id}")[0] == 200

    stages = boss.get_stages(deployment)
    assert stages['START']['status'] == 'ready'
    assert boss.get_deployment(deployment)['general']['status'] == 'ready'

    boss.post(f"/api/cancel_deployment/{deployment}")



def test_stage_with_a_job_can_not_be_reset(server, boss):

    deployment = boss.create_deployment('slow_wf')
    start_id = boss.get_stages(deployment)['START']['id']

    import sqlite3
    db = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'), timeout=10)
    db.execute("UPDATE stages SET status = 'in process', update_time = '2020-01-01 00:00:00' WHERE id = ?", (start_id,))
    db.execute("INSERT INTO processing_jobs (meta_file_id, stage_id, continue_run, status, create_time) VALUES (?, ?, 1, 'running', '2020-01-01T00:00:00')", (deployment, start_id))
    db.commit()
    db.close()

    status, data = boss.post_json(f"/api/reset_stage_status/{deployment}/{start_id}")

    assert status == 409
    assert 'processing service' in data['message']

    db = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'), timeout=10)
    db.execute("UPDATE processing_jobs SET status = 'failed' WHERE meta_file_id = ?", (deployment,))
    db.execute("UPDATE stages SET status = 'ready' WHERE id = ?", (start_id,))
    db.commit()
    db.close()

    boss.post(f"/api/cancel_deployment/{deployment}")



#---------------------------------------------------------
# auto-finish-stages-without-steps
#---------------------------------------------------------

def test_stage_without_steps_finishes_automatically(boss):

    cancel_open_deployments(boss, 'seq')

    deployment = boss.create_deployment('seq_wf')
    boss.finish_deployment(deployment)

    assert boss.get_stages(deployment)['END']['status'] == 'finished'
    assert boss.get_deployment(deployment)['general']['status'] == 'finished'

    history = json.loads(boss.get(f"/api/show_processing_history/{deployment}")[2])
    assert any('automatically' in (row['details'] or '') for row in history)



#---------------------------------------------------------
# list-deployments-fails-with-custom-data
#---------------------------------------------------------

def test_list_deployments_with_custom_data(boss):

    cancel_open_deployments(boss, 'seq')
    deployment = boss.create_deployment('seq_wf', {'ticket': 'ABC-1'})

    status, _, text = boss.get('/api/list_deployments/seq')
    assert status == 200

    row = next(d for d in json.loads(text) if d['meta_file_id'] == deployment)
    assert set(row.keys()) == {'meta_file_id', 'version', 'status', 'workflow_name', 'commit', 'create_time', 'update_time'}
    assert row['workflow_name'] == 'seq_wf'



def test_list_deployments_of_an_empty_project(boss):

    status, _, text = boss.get('/api/list_deployments/doesnotexist')

    assert status == 200
    assert json.loads(text) == []



#---------------------------------------------------------
# custom-data-on-create-unrestricted
#---------------------------------------------------------

def test_db_deployment_can_not_be_set_when_creating(boss):

    status, data = boss.post_json('/api/start_workflow/hidden_wf', {'ticket': 'x', 'db_deployment': {'tables': []}})

    assert status == 422
    assert 'db_deployment' in data['message']



def test_custom_data_size_is_limited(boss):
    assert boss.post_json('/api/start_workflow/hidden_wf', {'ticket': 'x' * 70000})[0] == 422



#---------------------------------------------------------
# missing-permission-checks, api-consistency
#---------------------------------------------------------

def test_no_access_without_read_permission(server, boss):
    """`stranger` may only read seq_wf"""

    cancel_open_deployments(boss, 'hidden')
    deployment = boss.create_deployment('hidden_wf')
    assert boss.run_stage(deployment, 'START')[0] == 200
    boss.wait_for_stage(deployment, 'START')

    data = boss.get_deployment(deployment)
    run_id = data['run_history'][0]['id']
    action_run_id = boss.get_stages(deployment)['START']['actions'][0]['run_history'][0]['id']

    stranger = server.client('stranger')

    for path in [f"/api/get_activity_log/{run_id}", f"/api/get_action_log/{action_run_id}", f"/api/show_processing_history/{deployment}",
                 f"/api/get_stage_steps_html/{deployment}/1", f"/api/watch_state/{deployment}"]:
        assert stranger.get(path)[0] == 403, path

    assert stranger.post(f"/api/get_meta_file_json/{deployment}")[0] == 403

    assert json.loads(stranger.get('/api/list_deployments/hidden')[2]) == []
    assert 'hidden' not in json.loads(stranger.get('/api/get_projects')[2])
    assert [wf['name'] for wf in json.loads(stranger.get('/api/get_workflows')[2])] == ['seq_wf']
    assert 'hidden_wf' not in stranger.get('/', headers={'Accept': 'text/html'})[2]
    assert 'hidden_wf' not in stranger.get('/workflows', headers={'Accept': 'text/html'})[2]



def test_same_data_with_read_permission(boss):

    deployment = boss.create_deployment('hidden_wf')
    boss.post(f"/api/cancel_deployment/{deployment}")

    assert any(d['meta_file_id'] == deployment for d in json.loads(boss.get('/api/list_deployments/hidden')[2]))
    assert boss.get(f"/api/show_processing_history/{deployment}")[0] == 200



def add_object(server, deployment: int) -> None:

    import sqlite3
    db = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'), timeout=10)
    db.execute("""INSERT INTO deploy_objects (meta_file_id, level, prod_lib, lib, name, type, attribute, deploy_status, ready, properties)
                  VALUES (?, 1, 'prodlib', 'devlib', 'orders', 'file', 'pf', 'new', 1, '{}')""", (deployment,))
    db.commit()
    db.close()



def test_objects_need_the_run_permission(server, boss):

    cancel_open_deployments(boss, 'seq')
    deployment = boss.create_deployment('seq_wf')
    add_object(server, deployment)

    body = {'lib': 'devlib', 'name': 'orders', 'type': 'file', 'checked': False}

    assert server.client('intern').post(f"/api/set_source_ready_4_deployment/{deployment}", body)[0] == 403
    assert boss.get_deployment(deployment)['objects'][0]['ready'] in [True, 1]

    assert server.client('runner').post(f"/api/set_source_ready_4_deployment/{deployment}", body)[0] == 200
    assert boss.get_deployment(deployment)['objects'][0]['ready'] in [False, 0]

    boss.post(f"/api/cancel_deployment/{deployment}")



def test_status_codes_and_error_format(server, boss):

    intern = server.client('intern')

    assert intern.post(f"/api/save_permissions")[0] == 403
    assert boss.post('/api/get_meta_file_json/999999')[0] == 404
    assert boss.post('/api/edit_custom_data/1', {'fields': 'x'})[0] in [404, 422]
    assert server.client().get('/api/get_projects', headers={'Accept': '*/*'})[0] == 401

    status, data = boss.post_json('/api/get_meta_file_json/999999')
    assert set(data.keys()) == {'status', 'message'}
    assert data['status'] == 'error'



def test_unknown_deployment_page(boss):
    assert boss.get('/show_details/seq/999999', headers={'Accept': 'text/html'})[0] == 404



def test_commit_conflict(boss):

    cancel_open_deployments(boss, 'hidden')

    assert boss.post('/api/create_deployment/hidden_wf/abc123')[0] == 200

    status, data = boss.post_json('/api/create_deployment/hidden_wf/abc123')

    assert status == 409
    assert set(data.keys()) == {'status', 'message'}

    cancel_open_deployments(boss, 'hidden')



def test_unexpected_error_has_an_id_and_no_details(server, boss):

    # A file which isn't valid JSON makes reading the deployment fail with an unexpected error
    import sqlite3
    deployment = boss.create_deployment('hidden_wf')
    db = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'), timeout=10)
    db.execute("UPDATE meta_files SET status = 'invalid status' WHERE id = ?", (deployment,))
    db.commit()
    db.close()

    status, data = boss.post_json(f"/api/get_meta_file_json/{deployment}")

    assert status == 500
    assert 'invalid status' not in data['message']

    error_id = data['message'].split()[-1]
    assert error_id in server.read_logs()

    db = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'), timeout=10)
    db.execute("UPDATE meta_files SET status = 'canceled' WHERE id = ?", (deployment,))
    db.commit()
    db.close()



def test_web_app_pages_work(server, boss):

    deployment = boss.create_deployment('hidden_wf')

    for path in ['/', '/list-objects', '/workflows', '/settings', '/user', f"/show_details/{deployment}"]:
        assert boss.get(path, headers={'Accept': 'text/html'})[0] == 200, path

    boss.post(f"/api/cancel_deployment/{deployment}")



def test_watch_state_sends_changes(server, boss):

    import http.client

    deployment = boss.create_deployment('hidden_wf')

    connection = http.client.HTTPConnection('127.0.0.1', server.port, timeout=10)
    connection.request('GET', f"/api/watch_state/{deployment}", headers={'Cookie': f"session_id={boss.session_id}"})
    response = connection.getresponse()

    try:
        first = response.readline()
        assert first.startswith(b'data: ')

        boss.post(f"/api/cancel_deployment/{deployment}")

        lines = []
        for _ in range(12):
            line = response.readline()
            lines.append(line)
            if line.startswith(b'data: '):
                break

        assert lines[-1].startswith(b'data: ') and lines[-1] != first

    finally:
        connection.close()



#---------------------------------------------------------
# The same with the processing service
#---------------------------------------------------------

@pytest.fixture(scope='module')
def service_server():

    import subprocess, sys

    s = Web_Server(settings="C_PROCESSING_MODE = 'service'\n").start()
    service = subprocess.Popen([sys.executable, os.path.join(s.directory, 'serviceapp', 'service.py')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for _ in range(50):
        if os.path.exists(os.path.join(s.directory, 'var', 'processing-service.pid')):
            break
        time.sleep(0.1)

    yield s

    service.terminate()
    service.wait(timeout=10)
    s.close()



@pytest.mark.parametrize('run', range(2))
def test_parallel_stages_with_the_processing_service(service_server, run):

    client = service_server.client('boss')
    deployment = client.create_deployment('par_wf')
    run_parallel_stages(client, deployment)

    time.sleep(0.5)
    stages = client.get_stages(deployment)

    for name in ['A', 'B']:
        assert stages[name]['status'] == 'finished'
        assert {action['status'] for action in stages[name]['actions']} == {'finished'}

    assert stages['END']['status'] == 'ready'
    assert client.get_deployment(deployment)['general']['status'] == 'ready'



def test_double_click_with_the_processing_service(service_server):

    client = service_server.client('boss')
    deployment = client.create_deployment('slow_wf')
    start_id = client.get_stages(deployment)['START']['id']

    def run(_):
        return service_server.client('boss').post_json(f"/api/run_stage/{deployment}/{start_id}/continue")[0]

    with ThreadPoolExecutor(5) as pool:
        results = list(pool.map(run, range(5)))

    assert results.count(200) == 1
    assert set(results) == {200, 409}

    stage = client.wait_for_stage(deployment, 'START')
    assert len(stage['actions'][0]['run_history']) == 1

    client.post(f"/api/cancel_deployment/{deployment}")



def test_failed_stage_can_be_run_again(server, boss):

    bad_workflow = 'seq_wf'
    cancel_open_deployments(boss, 'seq')

    deployment = boss.create_deployment(bad_workflow)
    start_id = boss.get_stages(deployment)['START']['id']

    # A step fails if its output on stderr isn't turned off
    import sqlite3
    db = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'), timeout=10)
    db.execute("UPDATE actions SET cmd = 'echo error >&2' WHERE stage_id = ?", (start_id,))
    db.commit()
    db.close()

    assert boss.run_stage(deployment, 'START')[0] == 200
    assert boss.wait_for_stage(deployment, 'START')['status'] == 'failed'

    for _ in range(20):
        if boss.get_deployment(deployment)['general']['status'] == 'failed':
            break
        time.sleep(0.1)

    assert boss.get_deployment(deployment)['general']['status'] == 'failed'

    db = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'), timeout=10)
    db.execute("UPDATE actions SET cmd = 'echo ok' WHERE stage_id = ?", (start_id,))
    db.commit()
    db.close()

    assert boss.run_stage(deployment, 'START')[0] == 200
    assert boss.wait_for_stage(deployment, 'START')['status'] == 'finished'

    boss.post(f"/api/cancel_deployment/{deployment}")
