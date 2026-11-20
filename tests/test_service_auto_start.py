"""Auto start of the processing service by the web app (docs/features/processing-service-auto-start.md)"""
import re, os, signal, subprocess, sys, time

import pytest

from web_server import Web_Server, is_running


# The watchdog checks every second instead of every minute
FAST_WATCHDOG = "C_SERVICE_WATCHDOG_INTERVAL = 1\n"

AUTO_START = {'C_PROCESSING_MODE': 'service', 'C_SERVICE_AUTO_START': True}



@pytest.fixture
def server():
    s = Web_Server(settings=FAST_WATCHDOG)
    yield s
    s.close()



def assert_not_started(server: Web_Server, seconds: float=3) -> None:
    """Several checks of the watchdog"""
    time.sleep(seconds)
    assert not server.is_service_running()
    assert 'auto start' not in server.read_logs()



def wait_for_new_service(server: Web_Server, old_pid: int, timeout: float=15) -> int:

    end = time.time() + timeout
    while time.time() < end:
        pid = server.get_service_pid()
        if pid not in (None, old_pid) and is_running(pid):
            return pid
        time.sleep(0.1)

    raise Exception(f"No new processing service after {timeout} seconds")



def count_service_starts(server: Web_Server) -> int:
    with open(server.path('log', 'service.log'), errors='replace') as f:
        return f.read().count('Processing service started: pid')



def test_service_is_started_with_the_web_app(server):

    server.write_app_settings(AUTO_START)
    server.start()

    server.wait_for_service()
    assert 'Processing service: start by auto start' in server.read_logs()

    # It keeps running when the web app ends
    pid = server.get_service_pid()
    server.stop()
    time.sleep(0.5)
    assert is_running(pid)



def test_auto_start_is_off_by_default(server):

    server.write_app_settings({'C_PROCESSING_MODE': 'service'})
    server.start()
    assert_not_started(server)



def test_no_auto_start_in_mode_thread(server):

    server.write_app_settings({'C_PROCESSING_MODE': 'thread', 'C_SERVICE_AUTO_START': True})
    server.start()
    assert_not_started(server)



def test_running_service_is_not_started_again(server):

    server.write_app_settings({'C_PROCESSING_MODE': 'service'})
    server.start()

    boss = server.client('boss')
    assert boss.post_json('/api/processing_service/start')[0] == 200
    pid = server.wait_for_service()

    status, data = boss.post_json('/api/set_service_auto_start/true')
    assert (status, data['auto_start'], data['auto_start_paused']) == (200, True, False), data
    assert server.read_app_settings() == AUTO_START
    assert 'Auto start of the processing service turned on by BOSS' in server.read_logs()

    time.sleep(3)
    assert server.get_service_pid() == pid and is_running(pid)
    assert 'auto start' not in server.read_logs().replace('Auto start of the processing service turned on', '')
    assert count_service_starts(server) == 1



def test_watchdog_starts_a_killed_service_again(server):

    server.write_app_settings(AUTO_START)
    server.start()

    pid = server.wait_for_service()
    os.kill(pid, signal.SIGKILL)

    wait_for_new_service(server, pid)



def test_stop_in_the_web_app_pauses_the_auto_start(server):

    server.write_app_settings(AUTO_START)
    server.start()
    server.wait_for_service()

    boss = server.client('boss')
    status, data = boss.post_json('/api/processing_service/stop')
    assert (status, data['service_running']) == (200, False), data
    assert os.path.exists(server.path('var', 'processing-service.stopped'))

    time.sleep(3)
    assert not server.is_service_running()

    _, _, text = boss.get('/settings/processing', headers={'Accept': 'text/html'})
    assert re.search(r'id="service-auto-start" data-action="service-auto-start" checked>', text)
    assert 'Auto start is paused' in text

    # Active again after the next start
    assert boss.post_json('/api/processing_service/start')[0] == 200
    assert not os.path.exists(server.path('var', 'processing-service.stopped'))
    pid = server.wait_for_service()

    os.kill(pid, signal.SIGKILL)
    wait_for_new_service(server, pid)



def test_stop_on_the_command_line_pauses_the_auto_start(server):

    server.write_app_settings(AUTO_START)
    server.start()
    pid = server.wait_for_service()

    output = server.run_service_script('stop')
    assert 'Auto start of the web app is paused' in output
    assert not is_running(pid)

    time.sleep(3)
    assert not server.is_service_running()

    output = server.run_service_script('start')
    assert 'paused' not in output
    pid = server.wait_for_service()

    os.kill(pid, signal.SIGKILL)
    wait_for_new_service(server, pid)



def test_restart_ends_the_pause(server):

    server.start()
    server.run_service_script('stop')
    assert os.path.exists(server.path('var', 'processing-service.stopped'))

    server.run_service_script('restart')
    assert not os.path.exists(server.path('var', 'processing-service.stopped'))
    server.wait_for_service()



def test_only_one_service_with_several_workers():

    server = Web_Server(settings=FAST_WATCHDOG, workers=4)
    try:
        server.write_app_settings(AUTO_START)
        server.start()

        server.wait_for_service()
        # Several checks of all workers
        time.sleep(4)

        assert count_service_starts(server) == 1
    finally:
        server.close()



def test_only_one_of_several_services_started_at_the_same_time(server):

    # Creates the database
    server.start()

    processes = [subprocess.Popen([sys.executable, server.path('serviceapp', 'service.py')], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, start_new_session=True)
                 for _ in range(4)]

    try:
        time.sleep(4)
        running = [p for p in processes if p.poll() is None]
        assert len(running) == 1

        for p in processes:
            if p.poll() is not None:
                assert p.returncode == 1
                assert 'already running' in p.stderr.read()

        assert count_service_starts(server) == 1
        assert server.get_service_pid() == running[0].pid

    finally:
        for p in processes:
            if p.poll() is None:
                p.terminate()
                p.wait(timeout=15)



def test_failed_start_does_not_stop_the_web_app(server):

    with open(server.path('serviceapp', 'service.py'), 'w') as f:
        f.write("import sys\nprint('broken', file=sys.stderr)\nsys.exit(1)\n")

    server.write_app_settings(AUTO_START)
    server.start()

    # The web app answers, while the auto start is still waiting for the service
    start = time.time()
    status, _, _ = server.client('boss').get('/settings/processing', headers={'Accept': 'text/html'})
    assert status == 200
    assert time.time() - start < 5

    end = time.time() + 30
    while 'Auto start of the processing service failed' not in server.read_logs():
        assert time.time() < end, server.read_logs()
        time.sleep(0.5)

    assert server.client('boss').get('/settings/processing', headers={'Accept': 'text/html'})[0] == 200



def test_old_settings_file_is_taken_over(server):

    with open(server.path('etc', 'web_settings.json'), 'w') as f:
        f.write('{"C_PROCESSING_MODE": "service"}')

    server.start()

    assert not os.path.exists(server.path('etc', 'web_settings.json'))
    assert server.read_app_settings() == {'C_PROCESSING_MODE': 'service'}

    _, _, text = server.client('boss').get('/settings/processing', headers={'Accept': 'text/html'})
    assert '<option value="service" selected>' in text
    assert 'from web app' in text
    assert 'id="service-auto-start" data-action="service-auto-start">' in text



def test_turn_off_the_auto_start(server):

    server.write_app_settings(AUTO_START)
    server.start()
    pid = server.wait_for_service()

    boss = server.client('boss')
    assert boss.post_json('/api/set_service_auto_start/false')[0] == 200
    assert server.read_app_settings() == {**AUTO_START, 'C_SERVICE_AUTO_START': False}

    os.kill(pid, signal.SIGKILL)
    time.sleep(3)
    assert not server.is_service_running()
