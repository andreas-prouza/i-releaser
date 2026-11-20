"""docs/bugfixes/stage-permissions-case.md: names of workflows and stages in the permissions are compared without case"""
import pytest

# Before meta_file, which permission_config imports (circular import, see routes.py)
from modules import deploy_version  # noqa: F401
from modules import permissions, permission_config


RUN = permissions.PermissionAction.RUN_WORKFLOW
READ = permissions.PermissionAction.READ


def allowed(workflows: dict, workflow: str, stage: str|None=None, action=RUN) -> bool:
    return permission_config.is_permission_allowed(permissions.Permissions(general=[], workflows=workflows), action, workflow, stage)



@pytest.mark.parametrize('key', ['PROD', 'prod', 'Prod'])
def test_stage_names_without_case(key):
    """The permissions page saves the name of the workflow (`PROD`), docs/permissions.md shows `prod`"""

    workflows = {'seq_wf': {'general': [], 'stages': {key: [RUN]}}}

    assert allowed(workflows, 'seq_wf', 'PROD')
    assert allowed(workflows, 'SEQ_WF', 'prod')
    assert not allowed(workflows, 'seq_wf', 'START')
    assert not allowed(workflows, 'seq_wf', 'PROD', READ)



@pytest.mark.parametrize('key', ['MyFlow', 'myflow'])
def test_workflow_names_without_case(key):

    workflows = {key: {'general': [RUN], 'stages': {}}}

    assert allowed(workflows, 'MyFlow')
    assert allowed(workflows, 'myflow')
    assert not allowed(workflows, 'other')
    assert not allowed(workflows, None)
