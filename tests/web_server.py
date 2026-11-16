"""
Runs the real web app for tests: a copy of the repository in a temporary directory with its own
configuration, database and logs. Nothing of the real installation is used.

The password isn't checked (I_RELEASER_LOCAL_DEBUGGING), the users come from USERS.
"""
import http.client, json, os, shutil, signal, socket, subprocess, sys, tempfile, time
from urllib.parse import urlencode


ROOT_DIR = os.path.realpath(f"{os.path.dirname(__file__)}/..")

ALL = ['admin', 'read', 'start workflow', 'run', 'cancel workflow', 'edit-custom-data', 'change check error']

USERS = {
    'boss': {'permissions': {'general': ALL, 'workflows': {}}},
    'intern': {'permissions': {'general': ['read', 'start workflow'], 'workflows': {}}},
    'stranger': {'permissions': {'general': [], 'workflows': {'seq_wf': {'general': ['read'], 'stages': {}}}}},
    'runner': {'permissions': {'general': ['read'], 'workflows': {'seq_wf': {'general': ['run'], 'stages': {}}}}},
}

WORKFLOWS = {
    'seq_wf': {
        'name': 'seq_wf',
        'default_project': 'seq',
        'editable_fields': ['$.ticket'],
        'step_action': [{'processing_step': 'quick', 'environment': 'PASE', 'execute': 'echo quick', 'check_error': True}],
        'stages': [
            {'name': 'START', 'next_stages': ['PROD'], 'host': 'localhost', 'processing_steps': ['quick']},
            {'name': 'PROD', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': ['quick']},
            {'name': 'END', 'description': 'Finished'},
        ],
    },
    'par_wf': {
        'name': 'par_wf',
        'default_project': 'par',
        'parallel_deployment_execution_allowed': True,
        'editable_fields': ['$.ticket'],
        'step_action': [
            {'processing_step': 'quick', 'environment': 'PASE', 'execute': 'echo quick', 'check_error': True},
            {'processing_step': 'slow1', 'environment': 'PASE', 'execute': 'sleep 2; echo slow1', 'check_error': True},
            {'processing_step': 'slow2', 'environment': 'PASE', 'execute': 'sleep 1; echo a; sleep 1; echo b', 'check_error': True},
        ],
        'stages': [
            {'name': 'START', 'next_stages': ['A', 'B'], 'host': 'localhost', 'processing_steps': ['quick']},
            {'name': 'A', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': ['slow1', 'quick']},
            {'name': 'B', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': ['slow2', 'quick']},
            {'name': 'END', 'processing_steps': ['quick'], 'after_stages_finished': ['A', 'B']},
        ],
    },
    'slow_wf': {
        'name': 'slow_wf',
        'default_project': 'slow',
        'step_action': [{'processing_step': 'slow', 'environment': 'PASE', 'execute': 'sleep 2', 'check_error': True}],
        'stages': [
            {'name': 'START', 'next_stages': ['A', 'B'], 'host': 'localhost', 'processing_steps': ['slow']},
            {'name': 'A', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': ['slow']},
            {'name': 'B', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': ['slow']},
            {'name': 'END'},
        ],
    },
    'hidden_wf': {
        'name': 'hidden_wf',
        'default_project': 'hidden',
        'step_action': [{'processing_step': 'quick', 'environment': 'PASE', 'execute': 'echo quick', 'check_error': True}],
        'stages': [
            {'name': 'START', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': ['quick']},
            {'name': 'END'},
        ],
    },
}



def copy_repository(target: str) -> None:
    """Only what's part of the repository and the templates. No local configuration."""

    for directory in ['modules', 'serviceapp', os.path.join('etc', 'examples'), os.path.join('scripts', 'examples')]:
        shutil.copytree(os.path.join(ROOT_DIR, directory), os.path.join(target, directory), ignore=shutil.ignore_patterns('__pycache__'))

    shutil.copytree(os.path.join(ROOT_DIR, 'webapp'), os.path.join(target, 'webapp'),
                    ignore=shutil.ignore_patterns('__pycache__', 'log', 'sessions', '*.pid'))

    for file in ['VERSION', os.path.join('etc', 'constants.py'), os.path.join('scripts', '__init__.py')]:
        shutil.copy(os.path.join(ROOT_DIR, file), os.path.join(target, file))

    # Like setup3.13.sh
    for source, destination in [(('etc', 'examples'), ('etc',)), (('webapp', 'etc', 'examples'), ('webapp', 'etc')), (('scripts', 'examples'), ('scripts',))]:
        source_dir = os.path.join(target, *source)
        for file in os.listdir(source_dir):
            if os.path.isfile(os.path.join(source_dir, file)):
                shutil.copy(os.path.join(source_dir, file), os.path.join(target, *destination, file))

    for file in [os.path.join('etc', 'workflow.json')]:
        if os.path.exists(os.path.join(target, file)):
            os.remove(os.path.join(target, file))



def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False



def get_free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]



class Web_Server:


    def __init__(self, workflows: dict=WORKFLOWS, users: dict=USERS, log_level: str='DEBUG', settings: str='', env: dict|None=None, workers: int=1):

        self.directory = tempfile.mkdtemp(prefix='ir-')
        self.port = get_free_port()
        self.process = None
        self.env = env or {}
        # Like gunicorn on a server: each worker runs the startup of the web app
        self.workers = workers

        copy_repository(self.directory)

        os.makedirs(os.path.join(self.directory, 'etc', 'workflows'))
        os.makedirs(os.path.join(self.directory, 'var'))

        for name, definition in workflows.items():
            with open(os.path.join(self.directory, 'etc', 'workflows', f"{name}.json"), 'w') as f:
                json.dump(definition, f)

        with open(os.path.join(self.directory, 'etc', 'user_permissions.json'), 'w') as f:
            json.dump({'users': users, 'roles': {}}, f)

        with open(os.path.join(self.directory, 'etc', 'object_commands.json'), 'w') as f:
            json.dump([], f)

        with open(os.path.join(self.directory, 'etc', 'settings.py'), 'w') as f:
            f.write(settings)

        with open(os.path.join(self.directory, 'webapp', 'etc', 'global_cfg.py'), 'a') as f:
            f.write("\nC_DEFAULT_PROJECT = 'seq'\n")

        logger_config = os.path.join(self.directory, 'webapp', 'etc', 'logger_config.py')
        with open(logger_config) as f:
            content = f.read()
        with open(logger_config, 'w') as f:
            f.write(content.replace('LOG_LEVEL = logging.INFO', f'LOG_LEVEL = logging.{log_level}'))


    @property
    def web_dir(self) -> str:
        return os.path.join(self.directory, 'webapp')


    def get_environment(self) -> dict:
        return {**os.environ, 'I_RELEASER_LOCAL_DEBUGGING': 'True', 'I_RELEASER_WEBAPP_PATH': self.web_dir, **self.env}


    def start(self) -> 'Web_Server':

        self.output = open(os.path.join(self.directory, 'uvicorn.log'), 'ab')
        command = [sys.executable, '-m', 'uvicorn', 'wsgi:app', '--port', str(self.port)]
        if self.workers > 1:
            command += ['--workers', str(self.workers)]

        self.process = subprocess.Popen(command, cwd=self.web_dir, env=self.get_environment(), stdout=self.output, stderr=self.output)

        for _ in range(100):
            if self.process.poll() is not None:
                raise Exception(f"Web app did not start: {self.read_output()}")
            try:
                socket.create_connection(('127.0.0.1', self.port), timeout=0.2).close()
                return self
            except OSError:
                time.sleep(0.1)

        raise Exception(f"Web app did not start: {self.read_output()}")


    def stop(self) -> None:

        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None
            self.output.close()


    def close(self) -> None:
        self.stop()
        self.stop_service()
        shutil.rmtree(self.directory, ignore_errors=True)


    def path(self, *parts: str) -> str:
        return os.path.join(self.directory, *parts)


    def get_service_pid(self) -> int|None:
        """Of the processing service, from its PID file"""

        pid_file = self.path('var', 'processing-service.pid')
        if not os.path.exists(pid_file):
            return None
        with open(pid_file) as f:
            return int(f.read().strip())


    def is_service_running(self) -> bool:
        pid = self.get_service_pid()
        return pid is not None and is_running(pid)


    def wait_for_service(self, running: bool=True, timeout: float=15) -> int|None:
        """Returns the PID of the service"""

        end = time.time() + timeout
        while time.time() < end:
            if self.is_service_running() == running:
                return self.get_service_pid()
            time.sleep(0.1)

        raise Exception(f"Processing service is {'not ' if running else ''}running after {timeout} seconds")


    def stop_service(self) -> None:
        """Processing service, if it's running"""

        pid = self.get_service_pid()
        if pid is None or not is_running(pid):
            return

        os.kill(pid, signal.SIGTERM)
        for _ in range(100):
            if not is_running(pid):
                return
            time.sleep(0.1)


    def run_service_script(self, action: str) -> str:
        """serviceapp/service on the command line"""

        result = subprocess.run([self.path('serviceapp', 'service'), action], capture_output=True, text=True, timeout=60,
                                env={**os.environ, 'I_RELEASER_PYTHON': sys.executable}, start_new_session=True)
        return result.stdout + result.stderr


    def write_app_settings(self, settings: dict) -> None:
        with open(self.path('etc', 'app.json'), 'w') as f:
            json.dump(settings, f)


    def read_app_settings(self) -> dict:
        with open(self.path('etc', 'app.json')) as f:
            return json.load(f)


    def read_output(self) -> str:
        with open(os.path.join(self.directory, 'uvicorn.log'), errors='replace') as f:
            return f.read()


    def read_logs(self) -> str:
        """All logs of the web app"""

        content = self.read_output()
        log_dir = os.path.join(self.web_dir, 'log')

        for file in os.listdir(log_dir):
            with open(os.path.join(log_dir, file), errors='replace') as f:
                content += f.read()

        return content


    def client(self, user: str|None=None) -> 'Client':
        client = Client(self)
        if user is not None:
            client.login(user)
        return client



class Client:
    """A browser: keeps its session cookie and tells where its requests come from"""


    def __init__(self, server: Web_Server):
        self.server = server
        self.session_id = None
        self.origin = f"http://127.0.0.1:{server.port}"
        self.headers = {}
        self.sent_session_ids = []


    def request(self, method: str, path: str, body=None, headers: dict|None=None, form: dict|None=None) -> tuple[int, dict, str]:

        all_headers = {'Accept': 'application/json', **self.headers, **(headers or {})}

        if self.session_id:
            all_headers['Cookie'] = f"session_id={self.session_id}"

        if method != 'GET' and self.origin:
            all_headers['Origin'] = self.origin

        data = None
        if body is not None:
            data = json.dumps(body)
            all_headers['Content-Type'] = 'application/json'
        if form is not None:
            data = urlencode(form)
            all_headers['Content-Type'] = 'application/x-www-form-urlencoded'

        connection = http.client.HTTPConnection('127.0.0.1', self.server.port, timeout=30)
        try:
            connection.request(method, path, body=data, headers=all_headers)
            response = connection.getresponse()
            text = response.read().decode('utf-8', errors='replace')
        finally:
            connection.close()

        headers_out = {k.lower(): v for k, v in response.getheaders()}

        for key, value in response.getheaders():
            if key.lower() == 'set-cookie' and value.startswith('session_id='):
                cookie = value.split(';')[0].split('=', 1)[1].strip('"')
                self.session_id = cookie or None
                self.sent_session_ids.append(cookie)

        return response.status, headers_out, text


    def get(self, path: str, **kwargs) -> tuple[int, dict, str]:
        return self.request('GET', path, **kwargs)


    def post(self, path: str, body=None, **kwargs) -> tuple[int, dict, str]:
        return self.request('POST', path, body=body if body is not None else {}, **kwargs)


    def post_json(self, path: str, body=None) -> tuple[int, dict]:
        status, _, text = self.post(path, body)
        return status, json.loads(text)


    def login(self, user: str, password: str='x') -> int:
        status, _, _ = self.request('POST', '/', form={'user': user, 'password': password}, headers={'Accept': 'text/html'})
        return status


    def get_deployment(self, meta_file_id: int) -> dict:
        return self.post_json(f"/api/get_meta_file_json/{meta_file_id}")[1]


    def get_stages(self, meta_file_id: int) -> dict:
        general = self.get_deployment(meta_file_id)['general']
        return {stage['name']: stage for stage in general['open_stages'] + general['processed_stages']}


    def create_deployment(self, workflow: str, custom_data: dict|None=None) -> int:
        status, data = self.post_json(f"/api/start_workflow/{workflow}", custom_data or {})
        assert status == 200, data
        return data['meta_file']['general']['id']


    def run_stage(self, meta_file_id: int, stage: str, option: str='continue') -> tuple[int, dict]:
        return self.post_json(f"/api/run_stage/{meta_file_id}/{self.get_stages(meta_file_id)[stage]['id']}/{option}")


    def wait_for_stage(self, meta_file_id: int, stage: str, status: tuple=('finished', 'failed'), timeout: float=15) -> dict:

        end = time.time() + timeout

        while time.time() < end:
            current = self.get_stages(meta_file_id)[stage]
            if current['status'] in status:
                return current
            time.sleep(0.1)

        raise Exception(f"Stage {stage} did not reach {status}: {current['status']}")


    def finish_deployment(self, meta_file_id: int, stages: tuple=('START', 'PROD')) -> None:

        for stage in stages:
            assert self.run_stage(meta_file_id, stage)[0] == 200
            self.wait_for_stage(meta_file_id, stage)

        # The next stage is activated right after the stage is finished
        end = time.time() + 5
        while time.time() < end and self.get_deployment(meta_file_id)['general']['status'] == 'in process':
            time.sleep(0.05)
