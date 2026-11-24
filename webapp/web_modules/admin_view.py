"""
Data of the admin pages (docs/features/web-ui-admin-pages.md): settings, processing, logs, workflows, the own account.
The templates decide nothing. Nothing here is HTML.
"""
import datetime, json, logging, re

from etc import constants
from modules import permission_config, permissions, processing_job, processing_service, processing_settings, version, workflow
from modules.db import app_info_data, app_sqlite, audit_data, login_failure_data, processing_job_data, processing_user_data, user_mfa_data

from web_modules import stage_flow, two_factor
from web_modules.status_view import get_status_view
from web_modules.template_filters import format_datetime, format_duration, format_utc


# Custom route files which couldn't be loaded (webapp/index.py): file name -> error
CUSTOM_ROUTE_ERRORS: dict[str, str] = {}

# Newest jobs of the processing service which are listed
NUMBER_OF_JOBS = 50

LOG_LINES = [100, 500, 1000, 10000]
LOG_LEVELS = {'all': 'All', 'WARNING': 'WARNING and above', 'ERROR': 'ERROR and above'}
LEVEL = re.compile(r'\b(DEBUG|INFO|WARNING|ERROR|CRITICAL)\b')



#-----------------------------------------------------------------------------------------------
# Administration (the addresses are /settings/...)
#-----------------------------------------------------------------------------------------------

def get_database_version() -> int|None:
    try:
        with app_sqlite.get_db_connection() as conn:
            return conn.execute("PRAGMA user_version").fetchone()[0]
    except Exception:
        return None



def get_general(default_project: str) -> dict:
    """Administration, part System: the state of the installation"""

    base = constants.C_LOCAL_BASE_DIR
    return {
        'details': [
            ('Default project', default_project),
            ('Version', version.APP_VERSION),
            # docs/features/start-times.md
            ('Web app started', get_web_start()),
            ('Processing service started', get_service_start(processing_service.notify()) or 'Not running'),
            ('Database', f"version {get_database_version()} (needs {app_sqlite.SCHEMA_VERSION})"),
            ('Installation', base),
            ('Workflows', constants.C_WORKFLOWS_DIR),
            ('Permissions', constants.C_USER_PERMISSIONS),
            ('Deployments', constants.C_META_DIR.split('{')[0]),
        ],
        'custom_route_errors': sorted(CUSTOM_ROUTE_ERRORS.items()),
        'retention': get_retention(),
    }



def get_security(tokens: list[dict]) -> dict:
    """Administration, part Security: who can log in and how"""

    return {
        # docs/features/api-v2.md#tokens
        'tokens': [get_token_info(token) for token in tokens],
        # docs/bugfixes/login-can-disable-ibm-i-profiles.md
        'blocked_logins': [{'user': b['user'], 'failures': b['failures'],
                            'last_failure': format_datetime(datetime.datetime.fromtimestamp(b['last_failure']))}
                           for b in login_failure_data.get_blocked_users()],
        'max_login_failures': constants.C_LOGIN_MAX_FAILURES,
        # docs/features/two-factor-authentication.md
        'two_factor_policy': TWO_FACTOR_POLICIES.get(two_factor.get_policy(), two_factor.get_policy()),
        'two_factor_users': user_mfa_data.get_enabled_users(),
    }



def get_web_start() -> dict|None:
    """The start of the web app as time for the browser (kv_list), docs/features/start-times.md"""

    try:
        start = app_info_data.get_web_start()
    except Exception as e:
        logging.warning(f"Start of the web app not found: {e}")
        return None

    return {'time': start.isoformat()} if start else None



def get_service_start(running: bool) -> dict|None:
    """The start of the running processing service with its process id, docs/features/start-times.md"""

    start = processing_service.get_start() if running else None
    if start is None:
        return None

    time, pid = start
    return {'time': time.isoformat(), 'note': f"process {pid}" if pid else None}



def get_token_info(token: dict) -> dict:
    """An API token for the pages (user page, settings): expiry and warnings (docs/features/api-v2.md#tokens)"""

    expires = datetime.datetime.fromisoformat(token['expires_at']) if token.get('expires_at') else None
    days_left = (expires - datetime.datetime.now(datetime.timezone.utc)).days if expires else None

    return {
        'id': token['id'],
        'user': token['user'],
        'name': token['name'],
        'scope': token['scope'],
        'masked': token.get('masked') or '–',
        'created': format_utc(token.get('created_at')),
        'last_used': format_utc(token['last_used_at']) if token.get('last_used_at') else 'Never',
        'expires': format_utc(expires) if expires else 'Never',
        'expires_soon': days_left is not None and 0 <= days_left < 14,
        'expired': days_left is not None and expires < datetime.datetime.now(datetime.timezone.utc),
        'legacy': bool(token.get('legacy')),
    }



def get_retention() -> dict:
    """Data retention (docs/features/data-retention.md)"""

    from modules import retention

    try:
        sizes = retention.get_sizes()
    except Exception as e:
        sizes = {'database_mb': '–', 'candidates': f"error: {e}"}

    days = constants.C_RETENTION_DAYS
    return {
        'details': [
            ('Remove deployments after', f"{days} days without change (finished or canceled)" if days else 'Never (C_RETENTION_DAYS = 0)'),
            ('Archive before', 'Yes, var/archive/' if constants.C_RETENTION_ARCHIVE else 'No'),
            ('Database', f"{sizes['database_mb']} MB"),
            ('To be removed now', sizes['candidates']),
        ],
        'active': bool(days),
    }



def get_notifications(user: str|None) -> dict:
    """Notifications (docs/features/notifications.md): the channels without secrets, the outbox, the own address for the test"""

    from modules import notifications

    try:
        status = notifications.get_status()
    except Exception as e:
        status = {'file': constants.C_NOTIFICATIONS_CONFIG, 'exists': True, 'error': str(e), 'readable_by_others': False, 'channels': [], 'outbox': None}

    outbox = status['outbox']
    status['details'] = [
        ('Waiting to be sent', outbox['waiting']),
        (f"Sent in the last {notifications.KEEP_DAYS} days", outbox['sent']),
        (f"Failed in the last {notifications.KEEP_DAYS} days", outbox['failed']),
    ] if outbox else []
    status['own_mail'] = permission_config.get_mail(user)
    return status



TWO_FACTOR_POLICIES = {
    'off': 'Off',
    'optional': 'Optional: each user decides',
    'admins': 'Required for users with the permission admin',
    'required': 'Required for all users',
}



def get_two_factor(user: str|None, setup_required: bool=False) -> dict:
    """The two-factor authentication of the own account (user page)"""

    mfa = user_mfa_data.get(user or '') if user else None
    enabled = mfa is not None and mfa['enabled']

    return {
        'policy': two_factor.get_policy(),
        'enabled': enabled,
        'required': bool(user) and two_factor.is_required(user),
        'setup_required': setup_required,
        'recovery_codes': mfa['recovery_codes'] if enabled else 0,
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
            'status_view': get_status_view('scheduled' if job.is_waiting_for_its_time() else job.status.value).__dict__,
            'queued': format_datetime(job.create_time),
            # A scheduled run (UTC): the page shows it in the time zone of the browser
            'scheduled': processing_job.format_utc(job.run_at) if job.run_at else '',
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
        'started': get_service_start(running),
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
    # Role names without case, as in the permission check
    effective = permission_config.get_effective(entry.permissions, [(r, konfig.get_role_permissions(r).permissions) for r in entry.roles
                                                                    if r.lower() in konfig._roles_by_name])

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




#-----------------------------------------------------------------------------------------------
# Audit (docs/features/audit-log.md)
#-----------------------------------------------------------------------------------------------

# Entries of each source shown on the page
AUDIT_ENTRIES = 1000


def _utc(value) -> str:
    """A time of the deployment history (local, without zone) or of the audit log (UTC) as UTC ISO 8601"""

    try:
        time = datetime.datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)

    if time.tzinfo is None:
        time = time.astimezone()

    return time.astimezone(datetime.timezone.utc).isoformat(timespec='seconds')



def get_audit() -> dict:
    """The security events and the actions on deployments, newest first, in one list"""

    rows = []

    for entry in audit_data.get_entries(AUDIT_ENTRIES):
        rows.append({'time': _utc(entry['time']), 'user': entry['user'] or '–', 'client': entry['client'] or '–', 'event': entry['event'],
                     'object': entry['object'] or '', 'result': entry['result'], 'details': entry['details'] or ''})

    for entry in processing_user_data.get_newest(AUDIT_ENTRIES):
        deployment = f"{entry.get('project')} {entry.get('version')}" if entry.get('project') else f"deployment {entry.get('meta_file_id')}"
        rows.append({'time': _utc(entry['timestamp']), 'user': entry['user'] or '–', 'client': '–', 'event': f"deployment: {entry['action']}",
                     'object': f"{deployment}{' / ' + entry['stage'] if entry.get('stage') else ''}", 'result': 'ok', 'details': entry['details'] or '',
                     'meta_file_id': entry.get('meta_file_id')})

    rows.sort(key=lambda row: row['time'], reverse=True)

    broken = audit_data.verify_chain()
    return {'rows': rows, 'chain_ok': broken is None, 'chain_broken_at': broken}
