"""Defects of the code review of 2026-11-23 in the modules, without the web app (docs/bugfixes/README.md#review-of-2026-11-23)"""
import io, json, logging, os, subprocess, sys, threading
from unittest import mock

import pytest

from web_server import ROOT_DIR

from modules import current_user, files, output_capture, permission_config, permissions


#---------------------------------------------------------
# minor-code-defects-2026-11, item 4: circular import
#---------------------------------------------------------

def all_modules() -> list[str]:

    names = []
    for package in ['modules', 'modules/db', 'modules/db/updates', 'modules/db_deployment']:
        for file in sorted(os.listdir(os.path.join(ROOT_DIR, package))):
            if file.endswith('.py') and file != '__init__.py':
                names.append(f"{package.replace('/', '.')}.{file[:-3]}")
    return names


@pytest.mark.parametrize('module', all_modules())
def test_each_module_can_be_imported_first(module):

    result = subprocess.run([sys.executable, '-B', '-c', f"import {module}"], cwd=ROOT_DIR, capture_output=True, text=True, timeout=60)

    assert result.returncode == 0, result.stderr[-2000:]



#---------------------------------------------------------
# nested-script-output-capture
#---------------------------------------------------------

def test_nested_captures():

    outer, inner = io.StringIO(), io.StringIO()

    with output_capture.capture(outer, io.StringIO()):
        print('outer')
        with output_capture.capture(inner, io.StringIO()):
            print('inner')
        print('outer again')

    assert outer.getvalue() == 'outer\nouter again\n'
    assert inner.getvalue() == 'inner\n'
    assert not isinstance(sys.stdout, output_capture._Thread_Stream)


def test_log_records_go_to_the_innermost_capture():

    outer, inner = io.StringIO(), io.StringIO()
    root = logging.getLogger()
    level = root.level
    root.setLevel(logging.INFO)

    try:
        with output_capture.capture(outer, io.StringIO()):
            with output_capture.capture(inner, io.StringIO()):
                logging.info('inner record')
            logging.info('outer record')
    finally:
        root.setLevel(level)

    assert 'inner record' in inner.getvalue()
    assert 'inner record' not in outer.getvalue()
    assert 'outer record' in outer.getvalue()


def test_exception_in_a_capture_restores_the_streams():

    with pytest.raises(ValueError):
        with output_capture.capture(io.StringIO(), io.StringIO()):
            with output_capture.capture(io.StringIO(), io.StringIO()):
                raise ValueError('x')

    assert not isinstance(sys.stdout, output_capture._Thread_Stream)
    assert not isinstance(sys.stderr, output_capture._Thread_Stream)


def test_other_threads_write_to_the_original_stream(capfd):

    captured = io.StringIO()
    seen = []

    with output_capture.capture(captured, io.StringIO()):
        thread = threading.Thread(target=lambda: seen.append(sys.stdout.write('other thread\n')))
        thread.start()
        thread.join()

    assert 'other thread' not in captured.getvalue()



#---------------------------------------------------------
# minor-code-defects-2026-11, item 3: getJson
#---------------------------------------------------------

def test_get_json_raises_after_the_last_attempt(tmp_path):

    file = tmp_path / 'invalid.json'
    file.write_text('{not json')

    with pytest.raises(json.JSONDecodeError):
        files.getJson(str(file), retry=True)



#---------------------------------------------------------
# minor-code-defects-2026-11, items 5 and 6: permissions
#---------------------------------------------------------

@pytest.fixture()
def permission_file(tmp_path, monkeypatch):

    def write(data: dict) -> None:
        file = tmp_path / 'user_permissions.json'
        file.write_text(json.dumps(data))
        monkeypatch.setattr(permission_config.constants, 'C_USER_PERMISSIONS', str(file))
        permission_config.PermissionKonfig.check_reload(force=True)

    yield write
    # The next test loads its own file
    permission_config.PermissionKonfig._PermissionKonfig__file_hash = None


def user(general=None, workflows=None, roles=None) -> dict:
    return {'roles': roles or [], 'permissions': {'general': general or [], 'workflows': workflows or {}}}


def test_permission_file_is_checked_only_every_few_seconds(permission_file):

    permission_file({'users': {'anna': user(['read'])}, 'roles': {}})

    with mock.patch.object(files, 'get_file_hash', wraps=files.get_file_hash) as get_hash:
        for _ in range(20):
            assert permission_config.is_user_allowed('anna', permissions.PermissionAction.READ)

    assert get_hash.call_count == 0


def test_names_of_users_and_roles_without_case(permission_file):

    permission_file({'users': {'ANNA': user(roles=['Releasers'])}, 'roles': {'RELEASERS': {'permissions': {'general': ['run'], 'workflows': {}}}}})

    assert 'anna' in permission_config.PermissionKonfig.get_user_list()
    assert permission_config.is_user_allowed('anna', permissions.PermissionAction.RUN_WORKFLOW, 'erp')


@pytest.mark.parametrize('workflow', [{'general': ['run']}, {'stages': {'PROD': ['run']}}])
def test_workflow_entry_with_only_general_or_stages(permission_file, workflow):

    permission_file({'users': {'anna': user(workflows={'erp': workflow})}, 'roles': {}})

    assert permission_config.is_user_allowed('anna', permissions.PermissionAction.RUN_WORKFLOW, 'erp', 'PROD')
    assert not permission_config.is_user_allowed('anna', permissions.PermissionAction.RUN_WORKFLOW, 'other', 'PROD')


def test_invalid_permission_file_keeps_the_permissions(permission_file, tmp_path):

    permission_file({'users': {'anna': user(['read'])}, 'roles': {}})
    (tmp_path / 'user_permissions.json').write_text('{invalid')
    permission_config.PermissionKonfig.check_reload(force=True)

    assert permission_config.is_user_allowed('anna', permissions.PermissionAction.READ)


def test_message_names_the_permission():

    current_user.set_user('nobody')
    with pytest.raises(Exception) as error:
        permission_config.check_user_permission(permissions.PermissionAction.RUN_WORKFLOW, 'erp')

    assert "permission 'run'" in str(error.value)



#---------------------------------------------------------
# core-redesign step 4: scripts are loaded when they are used
#---------------------------------------------------------

def test_commands_module_loads_no_scripts():

    code = "import sys; import modules.ibm_i_commands; print(sorted(m for m in sys.modules if m.startswith('scripts.')))"
    result = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT_DIR, capture_output=True, text=True, timeout=60)

    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip() == '[]'


@pytest.mark.parametrize('execute', ['os.system', 'a.b.c', 'no_dot', '../x.y', 'x.__class__', 'pre.__class__'])
def test_resolver_refuses_what_isnt_a_script(execute):

    from modules import scripts_loader

    with pytest.raises(scripts_loader.Script_Not_Found_Exception):
        scripts_loader.resolve(execute)
