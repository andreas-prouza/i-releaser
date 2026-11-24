"""
Four-eyes check (docs/features/four-eyes-check.md): a stage with `four_eyes_check: true` only runs after a second
person has approved it.

* The approving user has the permission `4-eyes check` for the stage and isn't the one who created the deployment.
* The user who runs (or schedules) the stage isn't the one who approved it.
* The approval belongs to the content of the deployment at that time: the object list (with the selection), the custom
  data and the compile list. A change makes it invalid; the stage needs a new approval.
* An approval is used by the run of the stage: after it has finished, a new run needs a new approval.
"""
import datetime
import hashlib
import json
import logging

from modules import action_type, errors
from modules.db import app_sqlite, processing_user_data


VALID = 'valid'
INVALID = 'invalid'
USED = 'used'



def is_required(mf, stage) -> bool:
    """The workflow of the deployment (as stored with it) requires the check for the stage"""

    for stage_dict in mf.workflow.stages or []:
        if stage_dict.get('name') == stage.name:
            return bool(stage_dict.get('four_eyes_check', False))

    return False



def get_content_hash(mf) -> str:

    objects = sorted([obj.prod_lib, obj.lib, obj.name, obj.type, obj.attribute, bool(obj.ready)] for obj in mf.deploy_objects)
    content = {'objects': objects, 'custom_data': mf.custom_data or {}, 'compiles': mf.get_compile_list()}
    return hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode('utf-8')).hexdigest()



def get_creator(mf) -> str|None:

    created = [row for row in processing_user_data.get_processing_user_by_meta_id(mf.id) if row.get('action') == action_type.Action_type.CREATE_WF.value]
    return created[0]['user'].lower() if created and created[0].get('user') else None



def get_approval(stage_id: int) -> dict|None:
    """The newest approval of the stage which isn't used, None if there is none"""

    with app_sqlite.get_db_connection() as conn:
        row = conn.execute("SELECT * FROM stage_approvals WHERE stage_id = ? AND status <> ? ORDER BY id DESC LIMIT 1", (stage_id, USED)).fetchone()

    return dict(row) if row else None



def get_state(mf, stage, user: str|None) -> dict|None:
    """
    For the page and the checks. None if the stage doesn't need the check.

    Returns:
        dict: approval (or None), valid (the content hasn't changed), problem (why the user can't run it now, None if he can)
    """

    if not is_required(mf, stage):
        return None

    approval = get_approval(stage.id)
    valid = approval is not None and approval['status'] == VALID and approval['content_hash'] == get_content_hash(mf)

    if approval is None:
        problem = "Needs the approval of a second person (four-eyes check)"
    elif not valid:
        problem = "The deployment has changed after the approval: it needs a new approval (four-eyes check)"
    elif user is not None and approval['user'] == user.lower():
        problem = "You have approved this stage: another person has to run it (four-eyes check)"
    else:
        problem = None

    return {'approval': approval, 'valid': valid, 'problem': problem}



def needs_approval(mf, stage) -> bool:
    """The stage requires the check and has no valid approval"""

    state = get_state(mf, stage, None)
    return state is not None and not state['valid']



def check_run(mf, stage, user: str|None) -> None:
    """
    Raises:
        errors.Conflict_Error: The stage needs an approval, a new one, or another user to run it
    """

    state = get_state(mf, stage, user)

    if state is not None and state['problem'] is not None:
        raise errors.Conflict_Error(f"Stage {stage.name}: {state['problem']}")



def approve(mf, stage, user: str) -> dict:
    """
    Raises:
        errors.Conflict_Error: The stage doesn't need it, can't be run, has a valid approval, or the user created the deployment
    """

    from modules import state as states

    user = user.lower()

    if not is_required(mf, stage):
        raise errors.Conflict_Error(f"Stage {stage.name} doesn't need an approval")

    if stage.status not in states.STAGE_RUNNABLE and stage.status.value != 'new':
        raise errors.Conflict_Error(f"Stage {stage.name} is '{stage.status.value}': it can't be approved now")

    if get_creator(mf) == user:
        raise errors.Conflict_Error("You have created this deployment: another person has to approve it (four-eyes check)")

    current = get_state(mf, stage, None)
    if current['valid']:
        raise errors.Conflict_Error(f"Stage {stage.name} has been approved already by {current['approval']['user']}")

    approval = {'meta_file_id': mf.id, 'stage_id': stage.id, 'user': user, 'time': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
                'content_hash': get_content_hash(mf), 'status': VALID}

    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        c.execute("UPDATE stage_approvals SET status = ? WHERE stage_id = ? AND status = ?", (INVALID, stage.id, VALID))
        c.execute("INSERT INTO stage_approvals (meta_file_id, stage_id, user, time, content_hash, status) VALUES (:meta_file_id, :stage_id, :user, :time, :content_hash, :status)", approval)
        conn.commit()

    processing_user_data.create_action_log(action_type.Action_type.APPROVE_STAGE, details="Approved (four-eyes check)", meta_file=mf, stage=stage)
    logging.info(f"Stage {stage.name} of deployment {mf.id} approved by {user}")
    return approval



def mark_used(mf, stage) -> None:
    """The stage has finished: its approval is used"""

    with app_sqlite.get_db_connection() as conn:
        conn.execute("UPDATE stage_approvals SET status = ? WHERE stage_id = ? AND status = ?", (USED, stage.id, VALID))
        conn.commit()



def invalidate_if_changed(mf, reason: str) -> None:
    """After a change of the object list, the selection or the custom data: approvals of other content become invalid (recorded in the history)"""

    current = get_content_hash(mf)

    with app_sqlite.get_db_connection() as conn:
        rows = conn.execute("SELECT id, stage_id FROM stage_approvals WHERE meta_file_id = ? AND status = ? AND content_hash <> ?", (mf.id, VALID, current)).fetchall()
        if not rows:
            return
        conn.executemany("UPDATE stage_approvals SET status = ? WHERE id = ?", [(INVALID, row['id']) for row in rows])
        conn.commit()

    from modules import hooks

    for row in rows:
        stage = mf.get_stage_by_id(row['stage_id'])
        processing_user_data.create_action_log(action_type.Action_type.APPROVAL_INVALID, details=f"Approval no longer valid: {reason}", meta_file=mf, stage=stage)
        hooks.emit(hooks.Event.APPROVAL_REQUESTED, mf, stage, details=f"The approval is no longer valid: {reason}")
