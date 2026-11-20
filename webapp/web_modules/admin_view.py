"""
Data of the admin pages (docs/features/web-ui-admin-pages.md): settings, processing, logs, workflows, the own account.
The templates decide nothing. Nothing here is HTML.
"""
import datetime, json, os, re

from etc import constants
from modules import permission_config, permissions, processing_service, processing_settings, version, workflow
from modules.db import app_sqlite, processing_job_data

from web_modules import stage_flow
from web_modules.status_view import get_status_view
from web_modules.template_filters import format_datetime, format_duration


# Newest jobs of the processing service which are listed
NUMBER_OF_JOBS = 50

LOG_LINES = [100, 500, 1000, 10000]
LOG_LEVELS = {'all': 'All', 'WARNING': 'WARNING and above', 'ERROR': 'ERROR and above'}
LEVEL = re.compile(r'\b(DEBUG|INFO|WARNING|ERROR|CRITICAL)\b')



#-----------------------------------------------------------------------------------------------
# Settings
#-----------------------------------------------------------------------------------------------

def get_database_version() -> int|None:
    try:
        with app_sqlite.get_db_connection() as conn:
            return conn.execute("PRAGMA user_version").fetchone()[0]
    except Exception:
        return None



def get_general(default_project: str, keys: dict) -> dict:

    base = constants.C_LOCAL_BASE_DIR
    return {
        'details': [
            ('Default project', default_project),
            ('Version', version.APP_VERSION),
            ('Database', f"version {get_database_version()} (needs {app_sqlite.SCHEMA_VERSION})"),
            ('Installation', base),
            ('Workflows', constants.C_WORKFLOWS_DIR),
            ('Permissions', constants.C_USER_PERMISSIONS),
            ('Deployments', constants.C_META_DIR.split('{')[0]),
        ],
        'tokens': [{'user': user, 'created': format_datetime(key.get('date')), 'last_used': format_datetime(key.get('last_used')),
                    'token': key.get('orig_key_masked') or '–'} for user, key in sorted(keys.items())],
    }



def get_processing() -> dict:

    jobs = list(reversed(processing_job_data.get_jobs(limit=NUMBER_OF_JOBS)))
    names = _get_stage_names([job.stage_id for job in jobs])
    now = datetime.datetime.now()

    rows = []
    for job in jobs:
        stage = names.get(job.stage_id, {})
        end = job.end_time or (now if job.start_time else None)
        rows.append({
            'id': job.id,
            'meta_file_id': job.meta_file_id,
            'deployment': f"{stage['project']} {stage['version']}" if stage.get('project') else str(job.meta_file_id),
            'stage': stage.get('name') or str(job.stage_id),
            'user': job.user or '–',
            'status': job.status.value,
            'status_view': get_status_view(job.status.value).__dict__,
            'queued': format_datetime(job.create_time),
            'started': format_datetime(job.start_time),
            'ended': format_datetime(job.end_time),
            'duration': format_duration((end - job.start_time).total_seconds()) if job.start_time and end else '–',
            'process': job.pid or '–',
            'error': job.error or '',
        })

    running = processing_service.notify()
    mode = processing_settings.get_processing_mode()
    auto_start = processing_settings.get_service_auto_start()

    return {
        'mode': mode,
        'modes': ['thread', 'service'],
        'mode_source': processing_settings.get_processing_mode_source(),
        'service': 'running' if running else 'not running',
        # A colour of status_view: running is good here, not running is bad only when stages wait for the service
        'service_kind': 'success' if running else ('danger' if mode == 'service' else 'neutral'),
        'running': running,
        'auto_start': auto_start,
        'auto_start_paused': auto_start and processing_settings.is_service_auto_start_paused(),
        'jobs': rows,
    }



def _get_stage_names(stage_ids: list[int]) -> dict:
    """Stage id -> name, project and version of its deployment, with one query"""

    ids = sorted({i for i in stage_ids if i is not None})
    if not ids:
        return {}

    with app_sqlite.get_db_connection() as conn:
        rows = conn.execute(f"""SELECT s.id, s.name, dv.project, dv.version FROM stages s
                                JOIN meta_files mf ON mf.id = s.meta_file_id
                                LEFT JOIN deploy_versions dv ON dv.id = mf.deploy_version_id
                                WHERE s.id IN ({', '.join('?' * len(ids))})""", ids).fetchall()

    return {row[0]: {'name': row[1], 'project': row[2], 'version': row[3]} for row in rows}



#-----------------------------------------------------------------------------------------------
# Logs
#-----------------------------------------------------------------------------------------------

def get_log_lines(lines: list[str]) -> list[dict]:
    """The lines with their level, newest first. A line without a level (e.g. of a traceback) has the level of the line before it."""

    result = []
    level = 'INFO'
    for line in lines:
        found = LEVEL.search(line[:80])
        if found:
            level = found.group(1)
        result.append({'text': line, 'level': level})

    return list(reversed(result))



#-----------------------------------------------------------------------------------------------
# Workflows
#-----------------------------------------------------------------------------------------------

def get_workflow_cards(workflows: list[dict], startable: list[str]) -> list[dict]:

    cards = []
    for wf in workflows:
        steps = {step['processing_step']: step for step in workflow.Workflow.get_workflow_steps_mapping(wf)}
        stages = []
        for i, stage in enumerate(wf.get('stages', []), 1):
            stage_steps = [steps.get(name, {'processing_step': name}) for name in stage.get('processing_steps', []) or []]
            stages.append({
                'id': i,
                'name': stage['name'],
                'next': stage.get('next_stages') or [],
                'description': stage.get('description') or '',
                'host': stage.get('host') or '',
                'after': stage.get('after_stages_finished') or [],
                'run_immediate': bool(stage.get('run_immediate')),
                'steps': [{'name': step.get('processing_step'), 'environment': step.get('environment') or '–', 'execute': step.get('execute') or '',
                           'parallel': bool(step.get('parallel')), 'group': step.get('parallel_group') or '',
                           'check_error': step.get('check_error', True)} for step in stage_steps],
                'status': 'new',
                'state': 'new',
                'view': get_status_view('new'),
                'waiting_for': [],
            })

        marks = []
        if any(step['parallel'] for stage in stages for step in stage['steps']):
            marks.append('parallel steps')
        if any(len(stage['next']) > 1 for stage in stages):
            marks.append('parallel stages')
        if wf.get('parallel_deployment_execution_allowed'):
            marks.append('parallel deployments')
        for key, label in [('editable_fields', 'editable fields'), ('create_fields', 'create fields'), ('hooks', 'hooks')]:
            if wf.get(key):
                marks.append(label)

        cards.append({
            'name': wf['name'],
            'project': wf.get('default_project') or '–',
            'flow': stage_flow.get_layout(stages),
            'stages': stages,
            'marks': marks,
            'editable_fields': wf.get('editable_fields') or [],
            'create_fields': wf.get('create_fields') or [],
            'hooks': sorted((wf.get('hooks') or {}).keys()) if isinstance(wf.get('hooks'), dict) else [],
            'startable': wf['name'] in startable,
            'json': json.dumps(wf, indent=2, ensure_ascii=False, default=str),
        })

    return cards



#-----------------------------------------------------------------------------------------------
# Own account
#-----------------------------------------------------------------------------------------------

def get_account(user: str|None) -> dict:
    """Roles and the permissions the user has in the end (own and from roles), as rows General / workflow / stage"""

    konfig = permission_config.PermissionKonfig
    entry = konfig.get_user_permissions(user or '')
    roles = konfig.role_permissions
    effective = permission_config.get_effective(entry.permissions, [(r, roles[r].permissions) for r in entry.roles if r in roles])

    def values(actions) -> list[str]:
        return [a.value if isinstance(a, permissions.PermissionAction) else str(a) for a in actions or []]

    def merge(own: list, other: dict) -> list[dict]:
        names = list(dict.fromkeys(values(own) + list(other)))
        order = [a.value for a in permission_config.ORDER]
        return [{'name': name, 'from': ', '.join(other.get(name, [])) if name not in values(own) else 'own'}
                for name in sorted(names, key=lambda n: order.index(n) if n in order else 99)]

    rows = [{'level': 0, 'name': 'General', 'permissions': merge(entry.permissions.general, effective['general'])}]

    own_workflows = {name.lower(): (name, value) for name, value in (entry.permissions.workflows or {}).items()}
    for name, eff in effective['workflows'].items():
        own_name, own = own_workflows.get(name.lower(), (name, {}))
        rows.append({'level': 1, 'name': own_name, 'permissions': merge((own or {}).get('general', []), eff['general'])})
        own_stages = {s.lower(): v for s, v in ((own or {}).get('stages') or {}).items()}
        for stage, stage_eff in eff['stages'].items():
            rows.append({'level': 2, 'name': stage, 'permissions': merge(own_stages.get(stage.lower(), []), stage_eff)})

    return {'roles': list(entry.roles), 'rows': rows}
