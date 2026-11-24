"""JSON schemas of the configuration files for editors (docs/features/workflow-json-schema.md)"""
import copy, glob, json, os

import jsonschema
import pytest

from web_server import ROOT_DIR, WORKFLOWS

from modules import workflow


SCHEMA_DIR = os.path.join(ROOT_DIR, 'docs', 'schema')


def schema(name: str) -> dict:
    with open(os.path.join(SCHEMA_DIR, f"{name}.schema.json")) as f:
        return json.load(f)


def load(path: str):
    with open(os.path.join(ROOT_DIR, path)) as f:
        return json.load(f)


@pytest.mark.parametrize('name', sorted(os.path.basename(f)[:-len('.schema.json')] for f in glob.glob(os.path.join(SCHEMA_DIR, '*.schema.json'))))
def test_schemas_are_valid(name):
    jsonschema.Draft202012Validator.check_schema(schema(name))


@pytest.mark.parametrize('path', sorted(os.path.relpath(f, ROOT_DIR) for f in glob.glob(os.path.join(ROOT_DIR, 'etc', 'examples', 'workflows', '*.json'))))
def test_example_workflows(path):
    jsonschema.validate(load(path), schema('workflow'))


@pytest.mark.parametrize('name', sorted(WORKFLOWS))
def test_workflows_of_the_tests(name):
    jsonschema.validate(WORKFLOWS[name], schema('workflow'))


@pytest.mark.parametrize('path, name', [('etc/examples/default_step_action.json', 'step-mapping'),
                                        ('etc/examples/object_commands.json', 'object-commands'),
                                        ('etc/examples/user_permissions.json', 'user-permissions'),
                                        ('etc/examples/notifications.json', 'notifications')])
def test_other_examples(path, name):
    jsonschema.validate(load(path), schema(name))


VALID = {'name': 'wf', 'default_project': 'p',
         'step_action': [{'processing_step': 'ok', 'environment': 'PASE', 'execute': 'echo ok'}],
         'stages': [{'name': 'START', 'processing_steps': ['ok'], 'next_stages': ['END']}, {'name': 'END'}]}


def changed(change) -> dict:
    wf = copy.deepcopy(VALID)
    change(wf)
    return wf


INVALID = {
    'no name': changed(lambda wf: wf.pop('name')),
    'no project': changed(lambda wf: wf.pop('default_project')),
    'unknown attribute': changed(lambda wf: wf.update(run_imediate=True)),
    'unknown stage attribute': changed(lambda wf: wf['stages'][0].update(run_imediate=True)),
    'unknown step attribute': changed(lambda wf: wf['step_action'][0].update(timeout=5)),
    'unknown hook event': changed(lambda wf: wf.update(hooks={'stage_done': ['x.y']})),
    'hook without function': changed(lambda wf: wf.update(hooks={'stage_finished': ['x']})),
    'next_stages not a list': changed(lambda wf: wf['stages'][0].update(next_stages='END')),
}


@pytest.mark.parametrize('case', sorted(INVALID))
def test_schema_and_code_refuse_the_same(case):

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(INVALID[case], schema('workflow'))

    with pytest.raises(workflow.Invalid_Workflow_Error):
        workflow.Workflow.validate_workflow(INVALID[case], 'test.json')


def test_valid_workflow_with_schema_reference(tmp_path):

    file = tmp_path / 'wf.json'
    file.write_text(json.dumps({'$schema': '../../docs/schema/workflow.schema.json', **VALID}))

    jsonschema.validate(json.loads(file.read_text()), schema('workflow'))
    assert workflow.Workflow.read_workflow_file(str(file))['name'] == 'wf'
