"""
Data of the deployment page (docs/features/web-ui-deployment-page.md).

The templates decide nothing: which actions exist, whether the user may use them (and why not),
what the attention bar says, the layout of the flow and how the steps of a stage are grouped.
Nothing here is HTML.
"""
from datetime import datetime, timedelta

from modules import current_user, meta_file, permissions, permission_config, processing_job, stage_status
from modules.db import processing_job_data, processing_user_data
from modules.job_status import Status as Job_Status
from modules.meta_file_status import Meta_file_status

from web_modules import stage_flow
from web_modules.status_view import get_status_view


PERMISSION = permissions.PermissionAction
Stage_Status = stage_status.Status

RESET_DEPLOYMENT_WAIT_SECONDS = 60

# Runs of more finished steps in a row than this are folded into one row
FOLD_FINISHED_STEPS = 10
# A step with more sub-steps than this shows them collapsed, unless one failed
COLLAPSE_SUB_STEPS = 10



#-----------------------------------------------------------------------------------------------
# Permissions
#-----------------------------------------------------------------------------------------------

def permission(action: permissions.PermissionAction, workflow: str, stage: str|None=None) -> dict:
    """{'allowed': bool, 'reason': text for a disabled button}"""

    if permission_config.is_user_allowed(current_user.get_user(), action, workflow, stage):
        return {'allowed': True, 'reason': None}

    where = f" for stage {stage}" if stage else ''
    return {'allowed': False, 'reason': f"Needs the permission '{action.value}'{where}"}



def action(name: str, label: str, allowed: dict, **data) -> dict:
    """A button of the page: `name` is its data-action, `data` its data-* attributes"""
    return {'name': name, 'label': label, 'allowed': allowed['allowed'], 'reason': allowed['reason'], 'data': data}



#-----------------------------------------------------------------------------------------------
# Stages
#-----------------------------------------------------------------------------------------------

def get_queued_jobs(mf: meta_file.Meta_File) -> dict:
    """Stage id -> job which waits for the processing service (or for its time: a scheduled run)"""
    return {job.stage_id: job for job in mf.processing_jobs if job.status == Job_Status.QUEUED}



def is_service_mode() -> bool:
    """A run can be scheduled only with the processing service (docs/features/scheduled-stage-run.md)"""

    from modules import processing_settings
    return processing_settings.get_processing_mode() == 'service'



def get_failed_schedule(mf: meta_file.Meta_File, stage) -> processing_job.Processing_Job|None:
    """
    The scheduled run of the stage which didn't start (missed time, the stage couldn't be run),
    as long as the stage hasn't been run since then and nothing else is queued for it.
    """

    if stage.status not in [Stage_Status.READY, Stage_Status.FAILED]:
        return None

    job = processing_job_data.get_last_jobs(mf.id).get(stage.id)
    if job is None or not job.is_scheduled() or job.status != Job_Status.FAILED or job.end_time is None:
        return None

    # The stage didn't change when its scheduled run failed to start
    if stage.update_time is not None and stage.update_time > job.end_time:
        return None

    return job



def get_stage_state(stage, queued: dict) -> str:
    """failed, running, queued, scheduled, ready, finished, new"""

    if stage.id in queued:
        return 'scheduled' if queued[stage.id].is_waiting_for_its_time() else 'queued'
    if stage.status in meta_file.STAGE_IN_PROCESS_STATUS:
        return 'running'
    return stage.status.value



def can_run(mf: meta_file.Meta_File, stage, queued: dict) -> bool:
    """The conditions of the run button of the flow chart before the redesign"""

    if stage.id in queued:
        return False

    # Like a deployment which is in process
    if len(mf.processing_jobs) > 0 and not mf.parallel_deployment_execution_allowed:
        return False

    if mf.status not in [Meta_file_status.FAILED, Meta_file_status.READY] or stage.id not in mf.get_open_stages().get_all_ids():
        return False

    return stage.status in [Stage_Status.FAILED, Stage_Status.READY]



def can_schedule(mf: meta_file.Meta_File, stage, queued: dict, service: bool) -> bool:
    """Run at…: where Run is possible, with the processing service"""
    return service and can_run(mf, stage, queued)



def get_reset(mf: meta_file.Meta_File, stage) -> str|None:
    """reset-last-finished: the last finished stage, reset-stage: a stage which hangs. None: no reset."""

    if stage.status == Stage_Status.FINISHED:
        last_finished = mf.get_last_finished_stage()
        if last_finished is None or last_finished.id != stage.id:
            return None
        try:
            mf.check_reset_last_finished_stage()
        except Exception:
            return None
        return 'reset-last-finished'

    if mf.status != Meta_file_status.IN_PROCESS or stage.id not in mf.get_open_stages().get_all_ids():
        return None

    if stage.status not in meta_file.STAGE_IN_PROCESS_STATUS:
        return None

    if stage.update_time > datetime.now() - timedelta(seconds=meta_file.STAGE_RESET_WAIT_SECONDS):
        return None

    return 'reset-stage'



def get_flow(mf: meta_file.Meta_File, queued: dict) -> stage_flow.Layout:

    stages = []
    for stage in mf.stages:
        state = get_stage_state(stage, queued)
        view = get_status_view(state if state in ('queued', 'scheduled') else stage.status)
        stages.append({
            'id': stage.id,
            'name': stage.name,
            'next': stage.next_stages,
            'status': stage.status.value,
            'state': state,
            'view': view,
            'waiting_for': mf.get_waiting_for(stage),
        })

    return stage_flow.get_layout(stages)



def get_selected_stage(mf: meta_file.Meta_File, flow: stage_flow.Layout) -> int|None:
    """Without a stage in the URL: the failed stage, else the running, else the first ready, else the last finished"""

    by_state = {}
    for node in flow.nodes:
        by_state.setdefault(node['state'], []).append(node['id'])

    for state in ['failed', 'running', 'queued', 'scheduled', 'ready']:
        if state in by_state:
            return by_state[state][0]

    # The last finished stage which has steps (stages without steps, like END, finish by themselves)
    finished = [stage for stage in mf.get_processed_stages() if stage.status == Stage_Status.FINISHED]
    with_steps = [stage for stage in finished if len(stage.actions) > 0]
    if with_steps or finished:
        return max(with_steps or finished, key=lambda stage: (stage.update_time, stage.id)).id

    return flow.nodes[0]['id'] if flow.nodes else None



#-----------------------------------------------------------------------------------------------
# Steps
#-----------------------------------------------------------------------------------------------

def flatten(actions: list[dict]) -> list[dict]:
    """Steps and their sub-steps, in their order"""

    result = []
    for a in actions:
        result.append(a)
        result += flatten(a.get('sub_actions') or [])
    return result



def last_run(action_dict: dict) -> dict|None:
    runs = action_dict.get('run_history') or []
    return max(runs, key=lambda run: (str(run.get('create_time') or ''), run.get('id') or 0)) if runs else None



def get_step(stage, action_dict: dict, sequence: str, check_error: dict, deployment_closed: bool, top: bool=True) -> dict:

    runs = sorted(action_dict.get('run_history') or [], key=lambda run: (str(run.get('create_time') or ''), run.get('id') or 0), reverse=True)
    cmd = action_dict.get('cmd') or ''
    status = action_dict.get('status')

    remote = action_dict.get('execute_remote')
    if remote is None:
        remote = bool(stage.execute_remote)

    can_check = dict(check_error)
    if deployment_closed:
        can_check = {'allowed': False, 'reason': 'The deployment is closed'}
    elif stage.status == Stage_Status.FINISHED:
        can_check = {'allowed': False, 'reason': 'The stage is finished'}

    sub_actions = action_dict.get('sub_actions') or []
    sub_steps = group_steps([get_step(stage, sub, f"{sequence}.{i}", check_error, deployment_closed, top=False) for i, sub in enumerate(sub_actions, 1)], fold=False)
    sub_failed = any(s['status'] == 'failed' for s in flatten_steps(sub_steps))

    return {
        'kind': 'step',
        'top': top,
        'id': action_dict.get('id'),
        'sequence': sequence,
        'name': action_dict.get('processing_step') or '',
        'environment': action_dict.get('environment') or '',
        'remote': remote,
        'cmd': cmd,
        'cmd_parts': [part.strip() for part in cmd.split(';') if part.strip()],
        'status': status,
        'view': get_status_view(status),
        'check_error': bool(action_dict.get('check_error')),
        'can_change_check': can_check,
        'runs': [{'id': run.get('id'), 'time': run.get('create_time'), 'view': get_status_view(run.get('status')),
                  'has_output': bool(run.get('stdout')), 'has_errors': bool(run.get('stderr'))} for run in runs],
        'open': status == 'failed',
        'sub_steps': sub_steps,
        'sub_collapsed': len(sub_actions) > COLLAPSE_SUB_STEPS and not sub_failed,
        'parallel': bool(action_dict.get('parallel')),
        'parallel_group': action_dict.get('parallel_group'),
        'search': f"{action_dict.get('processing_step') or ''} {cmd}".lower(),
    }



def flatten_steps(items: list[dict]) -> list[dict]:
    """The steps of a list of items (steps, groups, folded rows), with their sub-steps"""

    result = []
    for item in items:
        if item['kind'] == 'step':
            result.append(item)
            result += flatten_steps(item['sub_steps'])
        else:
            result += flatten_steps(item['items'])
    return result



def group_steps(steps: list[dict], fold: bool) -> list[dict]:
    """
    Steps with `parallel` which follow each other and have the same `parallel_group` run at the same time
    (docs/workflow.md#parallel-steps): one group. Runs of more than FOLD_FINISHED_STEPS finished items are folded.
    """

    items = []
    for step in steps:
        last = items[-1] if items else None
        if step['parallel']:
            if last is not None and last['kind'] == 'group' and last['name'] == (step['parallel_group'] or ''):
                last['items'].append(step)
            else:
                items.append({'kind': 'group', 'name': step['parallel_group'] or '', 'items': [step]})
        else:
            items.append(step)

    for item in items:
        if item['kind'] == 'group':
            statuses = [s['status'] for s in item['items']]
            item['status'] = 'failed' if 'failed' in statuses else 'finished' if all(s == 'finished' for s in statuses) else 'running' if 'in process' in statuses else 'new'
            item['running'] = statuses.count('in process')

    if not fold:
        return items

    folded = []
    run = []

    def end_run():
        if len(run) > FOLD_FINISHED_STEPS:
            folded.append({'kind': 'fold', 'items': list(run), 'count': len(flatten_steps(run))})
        else:
            folded.extend(run)
        run.clear()

    for item in items:
        if item['status'] == 'finished' and not any(s['status'] == 'failed' for s in flatten_steps([item])):
            run.append(item)
        else:
            end_run()
            folded.append(item)
    end_run()

    return folded



def get_steps_view(mf: meta_file.Meta_File, stage) -> dict:
    """The panel of the steps of a stage"""

    queued = get_queued_jobs(mf)
    workflow = mf.workflow.name
    closed = mf.status in [Meta_file_status.FINISHED, Meta_file_status.CANCELED]

    actions = stage.actions.get_actions_as_dict()
    check_error = permission(PERMISSION.CHANGE_CHECK_ERROR, workflow, stage.name)
    # The position: `sequence` of a step counts within its processing step
    steps = [get_step(stage, a, str(i), check_error, closed) for i, a in enumerate(actions, 1)]
    items = group_steps(steps, fold=True)

    all_steps = flatten_steps(items)
    failed = [s for s in all_steps if s['status'] == 'failed']

    run = permission(PERMISSION.RUN_WORKFLOW, workflow, stage.name)
    buttons = []
    if can_run(mf, stage, queued):
        buttons.append(action('run-stage', 'Run stage', run, stage_id=stage.id, stage_name=stage.name))
    if can_schedule(mf, stage, queued, is_service_mode()):
        buttons.append(action('schedule-stage', 'Run at…', run, stage_id=stage.id, stage_name=stage.name))

    schedule = None
    job = queued.get(stage.id)
    if job is not None and job.is_scheduled():
        schedule = {'run_at': processing_job.format_utc(job.run_at), 'user': job.user, 'job_id': job.id, 'continue_run': job.continue_run}
        buttons.append(action('cancel-schedule', 'Cancel schedule', run, job_id=job.id, stage_name=stage.name))

    failed_schedule = get_failed_schedule(mf, stage)
    if failed_schedule is not None:
        failed_schedule = {'run_at': processing_job.format_utc(failed_schedule.run_at), 'error': failed_schedule.error}

    reset = get_reset(mf, stage)
    if reset is not None:
        buttons.append(action(reset, 'Reset', run, stage_id=stage.id, stage_name=stage.name))

    history = [row for row in processing_user_data.get_processing_user_by_meta_id(mf.id) if row.get('stage') == stage.name]
    history.sort(key=lambda row: str(row.get('timestamp') or ''), reverse=True)

    details = [('Host', stage.host), ('Runs', 'remote' if stage.execute_remote else 'local')]
    if stage.remote_dir:
        details.append(('Remote dir', stage.remote_dir))
    if stage.build_dir:
        details.append(('Build dir', stage.build_dir))
    if stage.lib_mapping:
        details.append(('Library mapping', ', '.join(f"{k} → {v}" for k, v in stage.lib_mapping.items())))

    return {
        'meta_file_id': mf.id,
        'stage': {'id': stage.id, 'name': stage.name, 'description': stage.description, 'status': stage.status.value,
                  'view': get_status_view(get_stage_state(stage, queued) if stage.id in queued else stage.status), 'waiting_for': mf.get_waiting_for(stage)},
        'schedule': schedule,
        'failed_schedule': failed_schedule,
        'details': details,
        'history': history,
        'buttons': buttons,
        'items': items,
        'total': len([s for s in all_steps if s['top']]),
        'finished': len([s for s in all_steps if s['top'] and s['status'] == 'finished']),
        # Opened by itself only for a problem, at the latest error
        'problem': stage.status == Stage_Status.FAILED or len(failed) > 0,
        'latest_error': failed[-1]['id'] if failed else None,
    }



#-----------------------------------------------------------------------------------------------
# Attention bar
#-----------------------------------------------------------------------------------------------

def names(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1]



def get_attention(mf: meta_file.Meta_File, flow: stage_flow.Layout, queued: dict) -> dict|None:
    """
    What the deployment waits for: the first case which applies (failed, running, queued, scheduled, ready).
    Text: (text, strong); (ISO time, 'time') is a time shown in the time zone of the browser.
    """

    if mf.status in [Meta_file_status.FINISHED, Meta_file_status.CANCELED]:
        return None

    stages = {stage.id: stage for stage in mf.stages}
    workflow = mf.workflow.name
    service = is_service_mode()

    for state in ['failed', 'running', 'queued', 'scheduled', 'ready']:
        for node in flow.nodes:
            if node['state'] != state:
                continue

            stage = stages[node['id']]
            run = permission(PERMISSION.RUN_WORKFLOW, workflow, stage.name)
            steps = flatten(stage.actions.get_actions_as_dict())

            if state == 'failed':
                failed = [s for s in steps if s.get('status') == 'failed']
                step = failed[-1] if failed else None
                text = [('Stage ', False), (stage.name, True)] + ([(' failed in step ', False), (step.get('processing_step') or '', True), ('.', False)] if step else [(' failed.', False)])
                buttons = []
                log = last_run(step) if step else None
                if log and (log.get('stderr') or log.get('stdout')):
                    buttons.append(action('show-log', 'Show log', {'allowed': True, 'reason': None}, run_id=log['id'], log_type='errors' if log.get('stderr') else 'output',
                                          title=f"{step.get('processing_step')}"))
                if can_run(mf, stage, queued):
                    buttons.append(action('run-stage', 'Continue', run, stage_id=stage.id, stage_name=stage.name, option='continue'))
                    buttons.append(action('run-stage', 'Run all steps', run, stage_id=stage.id, stage_name=stage.name, option='run_all'))
                return {'kind': 'danger', 'icon': 'x-lg', 'text': text, 'buttons': buttons, 'stage_id': stage.id}

            if state == 'running':
                top = stage.actions.get_actions_as_dict()
                running = [i for i, a in enumerate(top, 1) if a.get('status') == 'in process']
                done = len([a for a in top if a.get('status') == 'finished'])
                if stage.status != Stage_Status.IN_PROCESS:
                    text = [('Stage ', False), (stage.name, True), (' is being prepared.', False)]
                elif not running:
                    # The status of a step is stored when it has ended
                    text = [('Stage ', False), (stage.name, True), (f" is running: {done} of {len(top)} steps finished.", False)]
                elif len(running) == 1:
                    text = [('Stage ', False), (stage.name, True), (f" is running: step {running[0]} of {len(top)}.", False)]
                else:
                    text = [('Stage ', False), (stage.name, True), (f" is running: steps {names([str(i) for i in running])} of {len(top)} at the same time.", False)]
                # A next stage which waits for parallel stages
                for next_stage in mf.get_next_stages(stage):
                    waiting = mf.get_waiting_for(next_stage)
                    if len(waiting) > 1 or (waiting and stage.name not in waiting):
                        text.append((f" {next_stage.name} starts when {names(waiting)} {'is' if len(waiting) == 1 else 'are'} finished.", False))
                        break
                buttons = []
                running_steps = [s for s in steps if s.get('status') == 'in process']
                log = last_run(running_steps[0]) if running_steps else None
                if log and (log.get('stdout') or log.get('stderr')):
                    buttons.append(action('show-log', 'Show output', {'allowed': True, 'reason': None}, run_id=log['id'], log_type='output',
                                          title=f"{running_steps[0].get('processing_step')}"))
                return {'kind': 'running', 'icon': 'arrow-repeat', 'text': text, 'buttons': buttons, 'stage_id': stage.id}

            if state == 'queued':
                text = [('Stage ', False), (stage.name, True), (' waits for the processing service.', False)]
                from modules import processing_service
                if not processing_service.notify():
                    text.append((' The processing service is not running.', False))
                buttons = [action('remove-from-queue', 'Remove from queue', run, job_id=queued[stage.id].id, stage_name=stage.name)]
                return {'kind': 'queued', 'icon': 'clock', 'text': text, 'buttons': buttons, 'stage_id': stage.id}

            if state == 'scheduled':
                job = queued[stage.id]
                text = [('Stage ', False), (stage.name, True), (' runs at ', False), (processing_job.format_utc(job.run_at), 'time'),
                        (f", scheduled by {job.user}." if job.user else '.', False)]
                from modules import processing_service
                if not processing_service.notify():
                    text.append((' The processing service is not running.', False))
                buttons = [action('cancel-schedule', 'Cancel schedule', run, job_id=job.id, stage_name=stage.name)]
                return {'kind': 'queued', 'icon': 'calendar-event', 'text': text, 'buttons': buttons, 'stage_id': stage.id}

            if state == 'ready':
                buttons = [action('run-stage', 'Run stage', run, stage_id=stage.id, stage_name=stage.name, option='continue')] if can_run(mf, stage, queued) else []
                if can_schedule(mf, stage, queued, service):
                    buttons.append(action('schedule-stage', 'Run at…', run, stage_id=stage.id, stage_name=stage.name))

                failed_schedule = get_failed_schedule(mf, stage)
                if failed_schedule is not None:
                    text = [('The scheduled run of ', False), (stage.name, True), (' at ', False), (processing_job.format_utc(failed_schedule.run_at), 'time'),
                            (f" did not start. {failed_schedule.error or ''}", False)]
                    return {'kind': 'danger', 'icon': 'calendar-x', 'text': text, 'buttons': buttons, 'stage_id': stage.id}

                text = [('Stage ', False), (stage.name, True), (' is ready to run.', False)]
                return {'kind': 'ready', 'icon': 'play-fill', 'text': text, 'buttons': buttons, 'stage_id': stage.id}

    return None



#-----------------------------------------------------------------------------------------------
# Page
#-----------------------------------------------------------------------------------------------

def get_header_actions(mf: meta_file.Meta_File, editable_fields: list) -> list[dict]:

    workflow = mf.workflow.name
    buttons = []

    if editable_fields:
        buttons.append(action('edit-custom-data', 'Edit custom data', permission(PERMISSION.EDIT_CUSTOM_DATA, workflow)))

    # A deployment which hangs (as before the redesign)
    if mf.status in [Meta_file_status.NEW, Meta_file_status.IN_PROCESS] and (datetime.now() - mf.update_time).total_seconds() > RESET_DEPLOYMENT_WAIT_SECONDS:
        buttons.append(action('reset-deployment', 'Reset status', permission(PERMISSION.RUN_WORKFLOW, workflow)))

    if mf.status in [Meta_file_status.READY, Meta_file_status.FAILED, Meta_file_status.NEW, Meta_file_status.IN_PROCESS]:
        buttons.append(action('cancel-deployment', 'Cancel deployment', permission(PERMISSION.CANCEL_WORKFLOW, workflow)))

    return buttons



def get_page(mf: meta_file.Meta_File) -> dict:

    queued = get_queued_jobs(mf)
    flow = get_flow(mf, queued)
    selected = get_selected_stage(mf, flow)
    stages = {stage.id: stage for stage in mf.stages}

    editable_fields = mf.get_editable_custom_fields()
    history = processing_user_data.get_processing_user_by_meta_id(mf.id)
    history.sort(key=lambda row: str(row.get('timestamp') or ''), reverse=True)

    total = len(flow.nodes)
    finished = len([node for node in flow.nodes if node['status'] == 'finished'])

    return {
        'meta_file_id': mf.id,
        'actions': get_header_actions(mf, editable_fields),
        'attention': get_attention(mf, flow, queued),
        'flow': flow,
        'progress': {'finished': finished, 'total': total, 'percent': round(finished * 100 / total) if total else 0},
        'selected_stage_id': selected,
        'steps': get_steps_view(mf, stages[selected]) if selected in stages else None,
        'editable_fields': editable_fields,
        'actions_history': history,
        'run_logs': sorted(mf.run_history.get_list(), key=lambda run: str(run.get('create_time') or ''), reverse=True),
    }
