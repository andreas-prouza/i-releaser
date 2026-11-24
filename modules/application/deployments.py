"""
Use cases of the deployments (docs/features/core-redesign.md, step 5).

Each function checks the permission of the current user (modules/current_user.py), does the action and writes the
history of the deployment. The Web API v1 and v2 (docs/features/api-v2.md) only translate their paths and bodies.

Raises (all functions):
    errors.Not_Found_Error, errors.Permission_Denied_Error, errors.Conflict_Error (not possible in the current status),
    errors.Invalid_Input_Error
"""
from __future__ import annotations

import base64
import binascii
from typing import Callable

# Before meta_file (the import order of the modules of a deployment)
from modules import deploy_version
from modules import action_type, current_user, errors, four_eyes, meta_file, permission_config, permissions, processing_job
from modules.db import deployment_list_data, meta_file_data, processing_job_data, processing_user_data, run_history_data
from modules.meta_file_status import Meta_file_status
from modules.object_status import Status as Obj_Status


Action = permissions.PermissionAction

ENDED = [Meta_file_status.CANCELED, Meta_file_status.FINISHED]
RUN_MODES = ('continue', 'all')
RESET_KINDS = ('hanging', 'last-finished')

DEFAULT_LIMIT = 50
MAX_LIMIT = 500



#---------------------------------------------------------
# Loading
#---------------------------------------------------------

def load(meta_file_id: int) -> meta_file.Meta_File:
    """The deployment, without a check of the permission (the caller checks the one of its action)"""

    mf = meta_file_data.get_meta_file_by_id(meta_file_id)

    if mf is None:
        raise errors.Not_Found_Error(f"Deployment {meta_file_id} not found")

    return mf



def get_stage(mf: meta_file.Meta_File, stage_id: int):

    stage = mf.get_stage_by_id(stage_id)

    if stage is None:
        raise errors.Not_Found_Error(f"Stage {stage_id} not found in deployment {mf.id}")

    return stage



def find_step(mf: meta_file.Meta_File, step_id: int) -> tuple:
    """(stage, step) of a step of any stage, also of a sub-step"""

    for stage in mf.stages:
        found = stage.actions.get_actions(action_id=step_id, include_subactions=True)
        if found:
            return stage, found[0]

    raise errors.Not_Found_Error(f"Step {step_id} not found in deployment {mf.id}")



def get_deployment(meta_file_id: int) -> meta_file.Meta_File:

    mf = load(meta_file_id)
    permission_config.check_user_permission(Action.READ, mf.workflow.name)
    return mf



def check_read_permission(meta_file_id: int|None) -> None:
    """For data of a deployment which is read without loading the deployment"""

    if meta_file_id is None:
        raise errors.Not_Found_Error("Not found")

    permission_config.check_user_permission(Action.READ, meta_file_data.get_workflow_name(meta_file_id))



def encode_cursor(last_id: int) -> str:
    return base64.urlsafe_b64encode(str(last_id).encode()).decode().rstrip('=')



def decode_cursor(cursor: str|None) -> int|None:

    if not cursor:
        return None

    try:
        value = base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)).decode()
        return int(value)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise errors.Invalid_Input_Error(f"Invalid cursor: '{cursor}'") from None



def check_limit(limit: int) -> int:

    if not 1 <= limit <= MAX_LIMIT:
        raise errors.Invalid_Input_Error(f"'limit' has to be between 1 and {MAX_LIMIT}")
    return limit



def list_deployments(project: str|None=None, status: str|None=None, limit: int=DEFAULT_LIMIT, cursor: str|None=None) -> tuple[list[dict], str|None]:
    """
    The deployments the current user may read, newest first.

    Returns:
        tuple: items, cursor of the next page (None if it's the last one)
    """

    if status is not None and status not in [s.value for s in Meta_file_status]:
        raise errors.Invalid_Input_Error(f"Status '{status}' is invalid. Valid: {', '.join(s.value for s in Meta_file_status)}")

    limit = check_limit(limit)
    readable = permission_config.get_readable_workflows(meta_file_data.get_workflow_names())

    rows = deployment_list_data.get_page(workflows=readable, project=project, status=status, before_id=decode_cursor(cursor), limit=limit + 1)
    more = len(rows) > limit
    rows = rows[:limit]

    return rows, encode_cursor(rows[-1]['id']) if more else None



#---------------------------------------------------------
# Actions
#---------------------------------------------------------

def create_deployment(workflow_name: str, custom_data: dict|None=None, compiles: list|None=None, commit: str|None=None,
                      object_list: str|None=None) -> meta_file.Meta_File:

    permission_config.check_user_permission(Action.START_WORKFLOW, workflow_name)

    if commit:
        from modules import workflow
        wf = workflow.Workflow(workflow_name)
        existing = deploy_version.Deploy_Version.get_deployment_by_commit(project=wf.default_project, commit=commit)

        if existing is not None and Meta_file_status(existing['status']) != Meta_file_status.CANCELED:
            raise errors.Conflict_Error(f"Given commit is already used in deployment version {existing['version']} with status '{existing['status']}'")

    # The commit is checked again when it's inserted (two requests at the same time)
    mf = meta_file_data.create_new_meta_file(workflow_name=workflow_name, object_list=object_list, custom_data=custom_data, compiles=compiles, commit=commit)
    processing_user_data.create_action_log(action=action_type.Action_type.CREATE_WF, details=workflow_name, meta_file=mf)

    return mf



def cancel_deployment(meta_file_id: int) -> meta_file.Meta_File:

    mf = load(meta_file_id)
    permission_config.check_user_permission(Action.CANCEL_WORKFLOW, mf.workflow.name)

    mf.cancel_deployment()
    # Only after the cancel: a failed cancel must not appear in the history
    processing_user_data.create_action_log(action=action_type.Action_type.CANCEL_WF, meta_file=mf)
    # A stage which is already running is not stopped. Like without the processing service.
    processing_job_data.cancel_queued_jobs(mf.id)

    return mf



def run_stage(meta_file_id: int, stage_id: int, mode: str='continue', run_at: str|None=None, processing_step: str|None=None) -> dict:
    """
    Args:
        mode: `continue` (the steps which haven't finished) or `all`
        run_at: ISO 8601 with time zone: a scheduled run by the processing service

    Returns:
        dict: `mode` and with the processing service `job_id`, `service_running`, `run_at`
    """

    if mode not in RUN_MODES:
        raise errors.Invalid_Input_Error(f"Mode '{mode}' is invalid. Valid modes are: {', '.join(RUN_MODES)}")

    mf = load(meta_file_id)
    stage = get_stage(mf, stage_id)
    permission_config.check_user_permission(Action.RUN_WORKFLOW, mf.workflow.name, stage=stage.name)

    if processing_step is not None and not stage.actions.get_actions(processing_step=processing_step):
        raise errors.Invalid_Input_Error(f"Stage {stage.name} has no step '{processing_step}'")

    return mf.start_stage(stage_id, processing_step=processing_step, continue_run=mode == 'continue',
                          run_at=processing_job.parse_run_at(run_at) if run_at is not None else None)



def reset_stage(meta_file_id: int, stage_id: int, kind: str):
    """
    Args:
        kind: `hanging` (a stage which hangs in process goes back to `ready`) or `last-finished` (the last finished stage goes back to `ready`)
    """

    if kind not in RESET_KINDS:
        raise errors.Invalid_Input_Error(f"Kind '{kind}' is invalid. Valid kinds are: {', '.join(RESET_KINDS)}")

    mf = load(meta_file_id)
    stage = get_stage(mf, stage_id)
    permission_config.check_user_permission(Action.RUN_WORKFLOW, mf.workflow.name, stage=stage.name)

    if kind == 'hanging':
        mf.reset_stage(stage)
        processing_user_data.create_action_log(action=action_type.Action_type.RESET_STAGE_STATUS, meta_file=mf)
        return stage

    stage = mf.reset_last_finished_stage(stage_id)
    processing_user_data.create_action_log(action=action_type.Action_type.RESET_LAST_FINISHED_STAGE, details=f"Reset finished stage to '{stage.status.value}'",
                                           meta_file=mf, stage=stage)
    return stage



def reset_deployment(meta_file_id: int) -> meta_file.Meta_File:
    """A deployment which hangs in process: its hanging stages go back, its status follows from its stages"""

    mf = load(meta_file_id)
    permission_config.check_user_permission(Action.RUN_WORKFLOW, mf.workflow.name)

    mf.reset_status()
    processing_user_data.create_action_log(action=action_type.Action_type.RESET_DEPLOYMENT_STATUS, meta_file=mf)

    return mf



def edit_custom_data(meta_file_id: int, fields: dict) -> list[str]:
    """
    Args:
        fields: {JSONPath: value}, only the `editable_fields` of the workflow

    Returns:
        list[str]: The paths which have changed
    """

    if not isinstance(fields, dict) or len(fields) == 0:
        raise errors.Invalid_Input_Error("No fields to change provided!")

    mf = load(meta_file_id)
    permission_config.check_user_permission(Action.EDIT_CUSTOM_DATA, mf.workflow.name)

    changed = mf.update_custom_data(fields)
    processing_user_data.create_action_log(action=action_type.Action_type.EDIT_CUSTOM_DATA, details=f"Changed custom data: {', '.join(changed)}", meta_file=mf)

    return changed



def approve_stage(meta_file_id: int, stage_id: int, confirm: Callable[[], None]|None=None) -> dict:
    """
    Four-eyes check (docs/features/four-eyes-check.md).

    Args:
        confirm: Runs after the check of the permission, e.g. the check of a recent code of the two-factor authentication
    """

    mf = load(meta_file_id)
    stage = get_stage(mf, stage_id)
    permission_config.check_user_permission(Action.FOUR_EYES_CHECK, mf.workflow.name, stage=stage.name)

    if confirm is not None:
        confirm()

    return four_eyes.approve(mf, stage, current_user.get_user())



def _check_objects_changeable(mf: meta_file.Meta_File) -> None:

    permission_config.check_user_permission(Action.RUN_WORKFLOW, mf.workflow.name)

    if mf.status in ENDED:
        raise errors.Conflict_Error(f"Can't change object status because deployment is already in status '{mf.status.value}'.")



def set_object_ready(meta_file_id: int, lib: str, name: str, type: str, ready: bool) -> None:
    """One object (Web API v1). An object which is deployed already can't be changed."""

    mf = load(meta_file_id)
    _check_objects_changeable(mf)

    obj = mf.deploy_objects.get_deploy_object(lib=lib, name=name, type=type)

    if obj is None:
        raise errors.Not_Found_Error(f"Object {lib}/{name}({type}) not found")

    if obj.deploy_status == Obj_Status.FINISHED:
        raise errors.Conflict_Error(f"Can't change object status because object is already in status '{obj.deploy_status.value}'.")

    obj.ready = ready
    mf.save()
    four_eyes.invalidate_if_changed(mf, f"object {lib}/{name}({type}) ready={ready}")
    # After the change: a failed change must not appear in the history
    processing_user_data.create_action_log(action=action_type.Action_type.CHANGE_OBJ_READY_STATUS, details=f"Set object {lib}/{name}({type}) ready={ready}", meta_file=mf)



def set_objects_ready(meta_file_id: int, objects: list[dict], ready: bool) -> dict:
    """
    Several objects in one change. Objects which are deployed already stay unchanged. If an object doesn't exist, nothing is changed.

    Returns:
        dict: changed (number), finished (the objects which were left unchanged)
    """

    if not isinstance(ready, bool):
        raise errors.Invalid_Input_Error("'ready' has to be true or false")

    if not isinstance(objects, list) or len(objects) == 0:
        raise errors.Invalid_Input_Error("'objects' has to be a list of objects")

    for o in objects:
        if not isinstance(o, dict) or not all(isinstance(o.get(key), str) for key in ['lib', 'name', 'type']):
            raise errors.Invalid_Input_Error("Each object needs 'lib', 'name' and 'type'")

    mf = load(meta_file_id)
    _check_objects_changeable(mf)

    found = [(o, mf.deploy_objects.get_deploy_object(lib=o['lib'], name=o['name'], type=o['type'])) for o in objects]

    not_found = [f"{o['lib']}/{o['name']}({o['type']})" for o, obj in found if obj is None]
    if not_found:
        raise errors.Not_Found_Error(f"{len(not_found)} objects not found: {', '.join(not_found[:5])}{' ...' if len(not_found) > 5 else ''}")

    changed = 0
    finished = []

    for _, obj in found:
        if obj.deploy_status == Obj_Status.FINISHED:
            finished.append({'lib': obj.lib, 'name': obj.name, 'type': obj.type})
            continue
        if obj.ready != ready:
            obj.ready = ready
            changed += 1

    if changed > 0:
        mf.save()
        processing_user_data.create_action_log(action=action_type.Action_type.CHANGE_OBJ_READY_STATUS, details=f"Set {changed} objects ready={ready}", meta_file=mf)
        four_eyes.invalidate_if_changed(mf, f"{changed} objects ready={ready}")

    return {'changed': changed, 'finished': finished}



def set_check_error(meta_file_id: int, stage_id: int, step_id: int, checked: bool) -> None:
    """Whether a failed step stops the stage (permission `change check error` of the stage)"""

    if not isinstance(checked, bool):
        raise errors.Invalid_Input_Error("'check_error' has to be true or false")

    mf = load(meta_file_id)

    if mf.status in ENDED:
        raise errors.Conflict_Error(f"Can't change step check because deployment is already {mf.status.value}.")

    mf.set_action_check(stage_id, step_id, checked, current_user.get_user())



def cancel_job(job_id: int) -> None:
    """Removes a stage run from the queue of the processing service, as long as it has not been started"""

    job = processing_job_data.get_job(job_id)
    if job is None:
        raise errors.Not_Found_Error(f"Processing job {job_id} not found")

    mf = load(job.meta_file_id)
    stage = get_stage(mf, job.stage_id)
    permission_config.check_user_permission(Action.RUN_WORKFLOW, mf.workflow.name, stage=stage.name)

    if not processing_job_data.cancel_job(job_id):
        raise errors.Conflict_Error(f"Processing job {job_id} is not in the queue anymore.")

    if job.is_scheduled():
        processing_user_data.create_action_log(action=action_type.Action_type.CANCEL_SCHEDULE, meta_file=mf, stage=stage,
                                               details=f"Canceled the run scheduled for {processing_job.format_utc_text(job.run_at)} (job {job.id})")



#---------------------------------------------------------
# History
#---------------------------------------------------------

def get_history(meta_file_id: int) -> list[dict]:
    """Who did what when (table processing_users), oldest first"""

    check_read_permission(meta_file_id if meta_file_data.get_workflow_name(meta_file_id) is not None else None)
    return processing_user_data.get_processing_user_by_meta_id(meta_file_id)



def get_jobs(meta_file_id: int) -> list[dict]:
    """The runs of the stages by the processing service, in the order they have been created"""

    check_read_permission(meta_file_id if meta_file_data.get_workflow_name(meta_file_id) is not None else None)
    return [job.get_dict() for job in processing_job_data.get_jobs(meta_file_id=meta_file_id)]



def get_step_log(meta_file_id: int, step_id: int) -> list[dict]:
    """The runs of a step with their output (read from its files in the meta directory, like the page)"""

    _, step = find_step(get_deployment(meta_file_id), step_id)
    runs = [run_history_data.get_run_history_by_id(run.id) for run in step.run_history]
    return [run.get_dict() for run in runs if run is not None]
