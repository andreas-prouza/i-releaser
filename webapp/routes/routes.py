import asyncio
import copy, logging, os, json, time
from typing import List

from fastapi import Body, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse, Response, StreamingResponse

# Custom modules
import etc.global_cfg as global_cfg
from etc import constants

from modules import current_user, errors, files, permissions, version
from modules import deploy_version, meta_file
from modules import workflow, processing_service, processing_settings, json_path
from modules.db import api_token_data, meta_file_data, meta_file_history_data, run_history_data, deploy_object_data, deployment_list_data, login_failure_data, user_mfa_data
from modules import notifications, retention, totp
from modules.application import deployments

from web_modules import http_functions, server_sessions
from web_modules import admin_view, app_login, audit, deployment_view, health, template_filters, two_factor
from web_modules.status_view import get_status_view
from modules import permission_config
from modules.object_status import Status as Obj_Status


# Handlers which only do blocking work are plain functions, so they run in a thread of FastAPI.
# Errors are not handled here: WebMiddleware.get_error_response creates the response.



def get_deployment(meta_file_id: int) -> meta_file.Meta_File:
    return deployments.load(meta_file_id)



def get_stage(mf: meta_file.Meta_File, stage_id: int):
    return deployments.get_stage(mf, stage_id)



def check_read_permission(meta_file_id: int|None) -> None:
    """For data of a deployment which is requested without loading the deployment"""
    deployments.check_read_permission(meta_file_id)



def is_admin() -> bool:
    return permission_config.is_user_allowed(current_user.get_user(), permissions.PermissionAction.ADMIN)



def get_readable_workflows() -> List[dict]:
    """Definitions of the workflows the current user may read"""

    workflows = workflow.Workflow.get_all_workflows_json()
    readable = permission_config.get_readable_workflows([wf['name'] for wf in workflows])

    return workflows if readable is None else [wf for wf in workflows if wf['name'] in readable]



def get_readable_deployments(deployments: List[dict]) -> List[dict]:
    """Only the deployments of workflows the current user may read"""

    readable = permission_config.get_readable_workflows(list({d['workflow_name'] for d in deployments if d['workflow_name']}))

    return deployments if readable is None else [d for d in deployments if d['workflow_name'] in readable]



def get_readable_workflow_names() -> List[str]|None:
    """Names of all workflows with deployments the current user may read. None: all of them"""

    return permission_config.get_readable_workflows(meta_file_data.get_workflow_names())



def get_readable_projects() -> List[str]:
    """Projects of the workflows the current user may read"""
    return list(dict.fromkeys(wf['default_project'] for wf in get_readable_workflows()))



def get_sidebar_data(request: Request) -> dict:
    """
    Data of the navigation of base.html. Pass it as `sidebar` (also in custom routes, see docs/scripts.md#own-pages).
    The page marks its entry with the block `nav_active`; the parameter `?sidebar_active=` of old links is ignored.
    """

    session = request.state.session
    user = session.get('current_user', None)
    admin = is_admin()

    return {
        'current_user': user.upper() if user is not None else None,
        'is_admin': admin,
        'logs': sorted(os.listdir('log/')) if admin else [],
        'app_version': version.APP_VERSION,
    }




def get_startable_workflows(project: str|None=None) -> List[dict]:
    """Workflows the current user may start (of one project), with the fields of `create_fields` for the start dialog"""

    result = []
    user = current_user.get_user()

    for wf in workflow.Workflow.get_all_workflows_json():
        if project is not None and wf.get('default_project') != project:
            continue
        if not permission_config.is_user_allowed(user, permissions.PermissionAction.START_WORKFLOW, wf['name']):
            continue

        fields = []
        for path in wf.get('create_fields') or []:
            try:
                keys = json_path.parse(path)
            except Exception:
                continue
            # Only fields with names; a position in a list can't be entered
            if keys and all(isinstance(key, str) for key in keys):
                fields.append({'path': path, 'keys': keys, 'label': '.'.join(keys)})

        result.append({'name': wf['name'], 'project': wf.get('default_project'), 'fields': fields})

    return result



def deployment_list(request: Request, project: str):
    """The deployments of a project (docs/features/web-ui-lists.md#deployments)"""

    readable = get_readable_workflow_names()
    counts = deployment_list_data.get_open_counts(readable)
    projects = [{'name': p, 'open': counts.get(p, 0)} for p in get_readable_projects()]

    deployments = get_readable_deployments(deploy_version.Deploy_Version.get_deployments(project)['deployments'])
    stages = deployment_list_data.get_current_stages(project)

    rows = []
    for d in deployments:
        stage = stages.get(d['meta_file_id']) if d.get('status') not in deployment_list_data.CLOSED else None
        rows.append({
            'id': d['meta_file_id'],
            'version': d.get('version'),
            'status': d.get('status'),
            'status_view': get_status_view(d.get('status')).__dict__,
            'open': d.get('status') not in deployment_list_data.CLOSED,
            'workflow': d.get('workflow_name') or '–',
            'stage': stage['name'] if stage else '–',
            'stage_view': get_status_view(stage['status']).__dict__ if stage else None,
            'created': template_filters.format_datetime(d.get('create_time')),
            'updated': template_filters.format_datetime(d.get('update_time')),
        })

    return http_functions.get_html_response(request, 'overview/list-deployments.html', sidebar=get_sidebar_data(request),
                                            project=project, projects=projects, rows=rows, startable=get_startable_workflows(project))



def index(request: Request):

    session = request.state.session
    project = session.get('current_project', None) or global_cfg.C_DEFAULT_PROJECT

    return deployment_list(request, project)



def list_objects(request: Request):
    """The page; the rows come page by page from /api/deploy_objects"""

    readable = get_readable_workflow_names()
    filters = {column: deployment_list_data.get_object_values(column, readable) for column in deployment_list_data.OBJECT_FILTER_EXACT}

    return http_functions.get_html_response(request, 'overview/list-objects.html', sidebar=get_sidebar_data(request), filters=filters)



def get_deploy_objects(request: Request, search: str='', filter: str='', sort: str='', order: str='desc', offset: int=0, limit: int=25):
    """One page of the object list: {total, rows}. `filter`: JSON {column: value} of the filters of the table"""

    try:
        filters = json.loads(filter) if filter else {}
    except ValueError:
        raise errors.Invalid_Input_Error("'filter' has to be JSON") from None
    if not isinstance(filters, dict):
        raise errors.Invalid_Input_Error("'filter' has to be a JSON object")

    return http_functions.get_json_response(deployment_list_data.get_objects(search=search, filters=filters, sort=sort, order=order, offset=offset, limit=limit,
                                                                             workflows=get_readable_workflow_names()))



def object_history(request: Request, project: str, prod_lib: str, name: str, type: str, attribute: str):
    """The deployments of an object, a part of the object list"""

    rows = deployment_list_data.get_object_history(project, prod_lib, name, type, attribute, workflows=get_readable_workflow_names())

    return http_functions.get_html_response(request, 'overview/object-history.html', rows=rows,
                                            title=f"{name}.{type} ({attribute}) in {prod_lib}")




def deploy_object_lifecycle(request: Request, project: str, prod_lib: str, name: str, type: str, attribute: str):
    logging.debug(f"Get deploy object lifecycle for {project=}, {prod_lib=}, {name=}, {type=}, {attribute=}")

    do = deploy_object_data.get_deploy_object_lifecycle(project, prod_lib, name, type, attribute, workflows=get_readable_workflow_names())

    if do is None:
        raise errors.Not_Found_Error(f"Deploy object not found for project '{project}', lib '{prod_lib}', name '{name}', type '{type}', attribute '{attribute}'")

    return http_functions.get_json_response(do)



def list_deployments(request: Request, project: str):
    return http_functions.get_json_response(get_readable_deployments(deploy_version.Deploy_Version.get_deployment_list(project)))



def select_project(request: Request, project: str):
    """The list of a project, without a redirect: the URL can be shared. `/` shows this project afterwards."""

    available_projects = get_readable_projects()

    if project not in available_projects:
        logging.info(f"Project '{project}' is not in list of {available_projects}.")
        return index(request)

    request.state.session['current_project'] = project

    return deployment_list(request, project)



def show_log(request: Request, log: str, number_of_lines: int=100, level: str='all', q: str=''):

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)
    audit.record(request, 'log_viewed', object=log)

    logging.debug(f"Read log file {log=}")

    if log not in os.listdir('log/'):
        raise errors.Not_Found_Error(f"Log {log} not found")

    if number_of_lines not in admin_view.LOG_LINES:
        number_of_lines = admin_view.LOG_LINES[0]
    if level not in admin_view.LOG_LEVELS:
        level = 'all'

    lines = files.readFile(f"log/{log}").splitlines()[-number_of_lines:]

    return http_functions.get_html_response(request, 'admin/log.html', sidebar=get_sidebar_data(request), logfile=log,
                                            logs=sorted(os.listdir('log/')), lines=admin_view.get_log_lines(lines),
                                            number_of_lines=number_of_lines, line_choices=admin_view.LOG_LINES,
                                            level=level, levels=admin_view.LOG_LEVELS, search=q)



def download_log(request: Request, log: str):
    """The whole log file"""

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)
    audit.record(request, 'log_viewed', object=log, details={'download': True})

    if log not in os.listdir('log/'):
        raise errors.Not_Found_Error(f"Log {log} not found")

    # Read at once: the log grows (and may be rotated) while it would be sent piece by piece
    with open(os.path.join('log', log), 'rb') as f:
        content = f.read()

    return Response(content=content, media_type='text/plain; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="{log}"'})



def get_next_url(request: Request) -> str:
    """
    The page to open after the login: `?next=` of /login, or the page the login was shown for.
    Only paths of this web app: no other host (//host, /\\host), no scheme.
    """

    path = request.scope['path']
    target = request.query_params.get('next', '/') if path == '/login' else path + (f"?{request.url.query}" if request.url.query else '')

    if not target.startswith('/') or target.startswith('//') or '\\' in target or any(ord(c) < 32 for c in target) or target.startswith(('/login', '/logout')):
        return '/'

    return target



async def login(request: Request):
    session = request.state.session
    next_url = get_next_url(request)

    if session.get('is_logged_in', False):
        # 303: the browser opens the page with GET, a reload doesn't send the form again
        return RedirectResponse(next_url, status_code=303)

    # Set by the login of this request (app_login.login), not stored in the session
    error_text = getattr(request.state, 'login_error', None)

    return http_functions.get_html_response(request, 'login.html', sidebar=None, error_text=error_text, next_url=next_url)



def show_user(request: Request):

    session = request.state.session

    return http_functions.get_html_response(request, 'admin/user.html', sidebar=get_sidebar_data(request),
                                            tokens=[admin_view.get_token_info(token) for token in api_token_data.get_of_user(session['current_user'])],
                                            max_token_days=constants.C_TOKEN_MAX_DAYS,
                                            account=admin_view.get_account(session.get('current_user')),
                                            two_factor=admin_view.get_two_factor(session.get('current_user'), session.get(two_factor.SESSION_SETUP_REQUIRED, False)))



def generate_user_key(request: Request):
    # Only in the web app, not with a token (a stolen token can't replace itself), with a recent code (docs/bugfixes/api-token-outlives-user.md)
    two_factor.require_recent_code(request)
    session = request.state.session
    logging.debug(f"Set new key for user {session['current_user']}")

    token = app_login.generate_new_user_key(request)
    audit.record(request, 'token_created')
    return http_functions.get_json_response({"token": token})



def drop_user_key(request: Request):
    two_factor.require_session(request)
    session = request.state.session
    logging.debug(f"Drop key for user {session['current_user']}")

    app_login.drop_user_key(request)
    audit.record(request, 'token_deleted')
    return http_functions.get_json_response({})



#-----------------------------------------------------------------------------------------------
# Two-factor authentication (docs/features/two-factor-authentication.md)
#-----------------------------------------------------------------------------------------------

def mfa_setup(request: Request):
    """A new secret for the authenticator app. Active after it has been confirmed with a code (mfa_enable)."""

    two_factor.require_session(request)
    user = current_user.get_user()

    if two_factor.get_policy() == 'off':
        raise errors.Conflict_Error("Two-factor authentication is turned off (C_2FA_POLICY)")

    if user_mfa_data.is_enabled(user):
        raise errors.Conflict_Error("Two-factor authentication is already set up. Turn it off first.")

    secret = totp.generate_secret()
    user_mfa_data.start_setup(user, secret)
    uri = totp.get_uri(user, secret)

    return http_functions.get_json_response({'secret': secret, 'uri': uri, 'qr_code': totp.get_qr_code(uri)})



def mfa_enable(request: Request, data: dict = Body(...)):
    """Confirms the setup with a code of the app. Returns the recovery codes, once."""

    two_factor.require_session(request)
    user = current_user.get_user()
    mfa = user_mfa_data.get(user)

    if mfa is None or mfa['enabled']:
        raise errors.Conflict_Error("Start the setup first")

    step = totp.verify(mfa['secret'], data.get('code') if isinstance(data.get('code'), str) else None)
    if step is None:
        raise errors.Invalid_Input_Error("The code is not valid. Check that the time of your phone is correct.")

    codes = totp.generate_recovery_codes()
    if not user_mfa_data.enable(user, step, [totp.hash_recovery_code(code) for code in codes]):
        raise errors.Conflict_Error("Start the setup again")

    request.state.session[two_factor.SESSION_CODE_TIME] = time.time()
    request.state.session.pop(two_factor.SESSION_SETUP_REQUIRED, None)
    logging.warning(f"Two-factor authentication set up by user {user}")
    audit.record(request, '2fa_enabled')

    return http_functions.get_json_response({'status': 'success', 'recovery_codes': codes})



def mfa_disable(request: Request, data: dict = Body(...)):

    two_factor.require_session(request)
    user = current_user.get_user()

    if two_factor.is_required(user):
        raise errors.Conflict_Error("Two-factor authentication is required for you (C_2FA_POLICY)")

    if not two_factor.verify_code(user, data.get('code') if isinstance(data.get('code'), str) else None):
        raise errors.Invalid_Input_Error("The code is not valid")

    user_mfa_data.remove(user)
    request.state.session.pop(two_factor.SESSION_CODE_TIME, None)
    logging.warning(f"Two-factor authentication turned off by user {user}")
    audit.record(request, '2fa_disabled')

    return http_functions.get_json_response({'status': 'success'})



def mfa_recovery_codes(request: Request):
    """New recovery codes; the old ones are no longer valid"""

    two_factor.require_recent_code(request)
    user = current_user.get_user()

    if not user_mfa_data.is_enabled(user):
        raise errors.Conflict_Error("Two-factor authentication is not set up")

    codes = totp.generate_recovery_codes()
    user_mfa_data.set_recovery_codes(user, [totp.hash_recovery_code(code) for code in codes])
    logging.warning(f"New recovery codes of user {user}")
    audit.record(request, '2fa_recovery_codes')

    return http_functions.get_json_response({'status': 'success', 'recovery_codes': codes})



def mfa_verify(request: Request, data: dict = Body(...)):
    """A code for actions which need a recent one (step-up)"""

    two_factor.require_session(request)
    user = current_user.get_user()

    if not two_factor.verify_code(user, data.get('code') if isinstance(data.get('code'), str) else None):
        raise errors.Invalid_Input_Error("The code is not valid")

    request.state.session[two_factor.SESSION_CODE_TIME] = time.time()
    return http_functions.get_json_response({'status': 'success'})



def mfa_reset(request: Request, user: str):
    """An admin removes the two-factor authentication of a user (e.g. a lost phone): the user sets it up again"""

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)
    two_factor.require_recent_code(request)

    if not user_mfa_data.remove(user):
        raise errors.Not_Found_Error(f"User {user} has no two-factor authentication")

    logging.warning(f"Two-factor authentication of user {user.lower()} reset by {current_user.get_user()}")
    audit.record(request, '2fa_reset', object=user.lower())
    return http_functions.get_json_response({'status': 'success'})



def revoke_token(request: Request, user: str):
    """An admin deletes the API token of a user (docs/bugfixes/api-token-outlives-user.md)"""

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)
    two_factor.require_recent_code(request)

    if not app_login.drop_token_of(user):
        raise errors.Not_Found_Error(f"User {user} has no token")

    logging.warning(f"API token of user {user.lower()} revoked by {current_user.get_user()}")
    audit.record(request, 'token_revoked', object=user.lower())
    return http_functions.get_json_response({'status': 'success'})



def healthz(request: Request):
    """Health check without login (docs/features/health-check.md). With a login or token: version and details."""

    status, answer = health.get_health(details=current_user.get_user() is not None)
    return http_functions.get_json_response(answer, status=status)



def run_retention(request: Request):
    """Removes the old deployments now (docs/features/data-retention.md)"""

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)
    two_factor.require_recent_code(request)

    if not constants.C_RETENTION_DAYS:
        raise errors.Conflict_Error("No deployment is removed: C_RETENTION_DAYS is 0")

    result = retention.run()
    audit.record(request, 'data_removed', details={'deployments': result['removed'], 'archived': len(result['archived']), 'errors': result['errors']})

    return http_functions.get_json_response({'status': 'success', **result})



def send_test_notification(request: Request, channel: str, data: dict|None = Body(None)):
    """Sends a test message with a channel of etc/notifications.json now (docs/features/notifications.md)"""

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)

    recipient = (data or {}).get('recipient')
    if recipient is not None and not isinstance(recipient, str):
        raise errors.Invalid_Input_Error("'recipient' has to be an e-mail address")

    try:
        sent_to = notifications.send_test(channel, recipient, current_user.get_user())
    except notifications.Notification_Config_Error as e:
        raise errors.Conflict_Error(str(e)) from e
    except notifications.Notification_Error as e:
        raise errors.Bad_Gateway_Error(str(e)) from e

    logging.info(f"Test notification of channel {channel} sent to {sent_to} by {current_user.get_user()}")
    return http_functions.get_json_response({'status': 'success', 'sent_to': sent_to})



def unblock_login(request: Request, user: str):
    """Ends the block of a user after too many failed logins (docs/bugfixes/login-can-disable-ibm-i-profiles.md)"""

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)
    two_factor.require_recent_code(request)

    if not login_failure_data.unblock_user(user):
        raise errors.Not_Found_Error(f"The login of user {user} is not blocked")

    logging.warning(f"Login of user {user.lower()} unblocked by {current_user.get_user()}")
    audit.record(request, 'login_unblocked', object=user.lower())
    return http_functions.get_json_response({'status': 'success'})



def logout(request: Request):
    """POST ends the session. GET only shows the button: a link of another site must not log out."""

    if request.method != 'POST':
        return http_functions.get_html_response(request, 'logout.html', sidebar=None)

    if hasattr(request.state, 'session'):
        logging.info(f"Logout of user {request.state.session.get('current_user', None)}")
        audit.record(request, 'logout', user=request.state.session.get('current_user', None))
        request.state.session.destroy()

    return RedirectResponse("/login", status_code=303)




def show_workflows(request: Request):

    logging.debug('Call workflows')

    wf = get_readable_workflows()
    invalid_files = workflow.Workflow.get_invalid_workflow_files() if is_admin() else {}
    startable = get_startable_workflows()

    return http_functions.get_html_response(request, 'admin/workflows.html', sidebar=get_sidebar_data(request),
                                            cards=admin_view.get_workflow_cards(wf, [w['name'] for w in startable]),
                                            invalid_files=invalid_files, startable=startable)



def show_settings(request: Request):
    """Administration, part System (docs/features/web-ui-admin-pages.md#settings)"""

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)

    return http_functions.get_html_response(request, 'admin/settings.html', sidebar=get_sidebar_data(request),
                                            general=admin_view.get_general(global_cfg.C_DEFAULT_PROJECT),
                                            notifications=admin_view.get_notifications(current_user.get_user()))



def show_security(request: Request):
    """Administration, part Security: API tokens, two-factor authentication, blocked logins (docs/features/web-ui-admin-pages.md#settings)"""

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)

    return http_functions.get_html_response(request, 'admin/security.html', sidebar=get_sidebar_data(request),
                                            security=admin_view.get_security(api_token_data.get_all()))



def show_audit(request: Request):
    """Settings, audit: security events and actions on deployments (docs/features/audit-log.md)"""

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)

    return http_functions.get_html_response(request, 'admin/audit.html', sidebar=get_sidebar_data(request), audit=admin_view.get_audit())



def download_audit(request: Request):
    """The entries of the audit page as CSV"""

    import csv, io

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['time (UTC)', 'user', 'client', 'event', 'object', 'result', 'details'])
    for row in admin_view.get_audit()['rows']:
        writer.writerow([row['time'], row['user'], row['client'], row['event'], row['object'], row['result'], row['details']])

    audit.record(request, 'log_viewed', object='audit', details={'download': True})
    return Response(content=output.getvalue(), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="i-releaser-audit.csv"'})



def show_processing(request: Request):
    """Settings, processing of stages: mode, processing service, jobs"""

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)

    return http_functions.get_html_response(request, 'admin/processing.html', sidebar=get_sidebar_data(request),
                                            processing=admin_view.get_processing())



def show_details(request: Request, project: str, version: int):

    meta: meta_file.Meta_File = deploy_version.Deploy_Version.get_deployment(project, version)

    return show_details_by_id(request, meta.id)



def show_details_by_id(request: Request, meta_file_id: int):
    logging.debug(f'Show details of {meta_file_id=}')

    mf: meta_file.Meta_File = get_deployment(meta_file_id)
    permission_config.check_user_permission(permissions.PermissionAction.READ, mf.workflow.name)

    page = deployment_view.get_page(mf)

    # For the script of the page: no values inside JavaScript (docs/features/web-ui-scripts.md#rules)
    can_edit = any(a['name'] == 'edit-custom-data' and a['allowed'] for a in page['actions'])
    page_data = {
        'meta_file_id': mf.id,
        'selected_stage_id': page['selected_stage_id'],
        'editable_fields': page['editable_fields'] if can_edit else [],
    }

    return http_functions.get_html_response(request, 'overview/show-deployment.html', sidebar=get_sidebar_data(request),
                                            deployment_dict=mf.get_all_data_as_dict(), page=page, page_data=page_data, objects_table=get_objects_table(mf))



def show_stage_steps(request: Request, meta_file_id: int, stage_id: int):
    """The panel of the steps of a stage, a part of the deployment page"""

    mf: meta_file.Meta_File = get_deployment(meta_file_id)
    permission_config.check_user_permission(permissions.PermissionAction.READ, mf.workflow.name)

    return http_functions.get_html_response(request, 'overview/deployment/stage-steps.html', steps=deployment_view.get_steps_view(mf, get_stage(mf, stage_id)))



def run_stage(request: Request, meta_file_id: int, stage_id: int, option: str, data: dict|None = Body(None)):
    """
    Runs a stage in the background.
    Body (optional): {"run_at": "2026-11-24T22:00:00+01:00"}: scheduled run by the processing service (docs/features/scheduled-stage-run.md)
    """

    if option not in ['continue', 'run_all']:
        raise errors.Invalid_Input_Error(f"Option '{option}' is invalid. Valid options are: 'continue', 'run_all'")

    result = deployments.run_stage(meta_file_id, stage_id, mode='all' if option == 'run_all' else 'continue', run_at=(data or {}).get('run_at'))

    return http_functions.get_json_response({'status': 'success', **result})



def get_meta_file_json(request: Request, meta_file_id: int):
    return http_functions.get_json_response(deployments.get_deployment(meta_file_id).get_all_data_as_dict())



def get_activity_log(request: Request, id: int):

    logging.debug(f"Get logs from: {id=}")

    check_read_permission(meta_file_data.get_meta_file_id_of_run(id))

    history = meta_file_history_data.get_run_history_by_id(id)
    if history:
        return http_functions.get_json_response(history.get_dict())

    return http_functions.get_json_response({})




def get_action_log(request: Request, id: int):

    logging.debug(f"Get logs from: {id=}")

    check_read_permission(meta_file_data.get_meta_file_id_of_action_run(id))

    history = run_history_data.get_run_history_by_id(id)
    if history:
        return http_functions.get_json_response(history.get_dict())

    return http_functions.get_json_response({})




def show_processing_history(request: Request, meta_file_id: int):
    return http_functions.get_json_response(deployments.get_history(meta_file_id))



def cancel_deployment(request: Request, meta_file_id: int):
    deployments.cancel_deployment(meta_file_id)
    return http_functions.get_json_response({'status': 'success'})



def cancel_job(request: Request, job_id: int):
    """Removes a stage run from the queue of the processing service, as long as it has not been started."""
    deployments.cancel_job(job_id)
    return http_functions.get_json_response({'status': 'success'})



def set_processing_mode(request: Request, mode: str):
    """Changes the processing mode for the next stages, without a restart (stored in etc/app.json)"""

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)
    two_factor.require_recent_code(request)

    old_mode = processing_settings.get_processing_mode()
    processing_settings.set_processing_mode(mode, current_user.get_user())
    audit.record(request, 'setting_changed', object='C_PROCESSING_MODE', details={'old': old_mode, 'new': mode})

    return http_functions.get_json_response({'status': 'success', 'mode': mode, 'service_running': processing_service.notify()})



def control_processing_service(request: Request, action: str):
    """Starts, stops or restarts the processing service. Running jobs are not affected."""

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)
    two_factor.require_recent_code(request)

    output = processing_settings.control_service(action, current_user.get_user())
    audit.record(request, 'setting_changed', object='processing service', details={'action': action})

    return http_functions.get_json_response({'status': 'success', 'output': output, 'service_running': processing_service.notify()})



def set_service_auto_start(request: Request, enabled: bool):
    """Turns the auto start of the processing service on or off (stored in etc/app.json)"""

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)
    two_factor.require_recent_code(request)

    processing_settings.set_service_auto_start(enabled, current_user.get_user())
    audit.record(request, 'setting_changed', object='C_SERVICE_AUTO_START', details={'new': enabled})

    return http_functions.get_json_response({'status': 'success', 'auto_start': enabled,
                                             'auto_start_paused': processing_settings.is_service_auto_start_paused()})



def edit_custom_data(request: Request, meta_file_id: int, data: dict = Body(...)):
    """
    Changes the editable fields of the custom data of a deployment.
    Body: {"fields": {"{JSONPath}": value, ...}}
    Only fields defined in `editable_fields` of the workflow can be changed.
    """

    deployments.edit_custom_data(meta_file_id, data.get('fields'))
    return http_functions.get_json_response({'status': 'success'})



def approve_stage(request: Request, meta_file_id: int, stage_id: int):
    """Four-eyes check: a second person approves a stage before it can run (docs/features/four-eyes-check.md)"""

    approval = deployments.approve_stage(meta_file_id, stage_id, confirm=lambda: two_factor.require_recent_code(request))
    return http_functions.get_json_response({'status': 'success', 'approved_by': approval['user'], 'time': approval['time']})



def reset_stage_status(request: Request, meta_file_id: int, stage_id: int):
    deployments.reset_stage(meta_file_id, stage_id, 'hanging')
    return http_functions.get_json_response({'status': 'success'})



def reset_last_finished_stage(request: Request, meta_file_id: int, stage_id: int):
    """Sets the stage which has been finished last back to 'ready', so it can be run again.
    Only possible as long as the deployment is not finished and no stage is in process.
    """
    deployments.reset_stage(meta_file_id, stage_id, 'last-finished')
    return http_functions.get_json_response({'status': 'success'})



def reset_deployment_status(request: Request, meta_file_id: int):
    deployments.reset_deployment(meta_file_id)
    return http_functions.get_json_response({'status': 'success'})



def create_deployment(request: Request, wf_name: str, commit: str|None=None, obj_list: str|None=None):
    """
    Creates a new deployment for a given workflow, commit, and the name of the list of objects.
    A commit can only be used by one deployment of a project which isn't canceled.
    obj_list: Path of a file with the objects to be included in the deployment (see docs/workflow.md#object-list).
    """

    mf = deployments.create_deployment(wf_name, commit=commit, object_list=obj_list)
    return http_functions.get_json_response({'status': 'success', 'meta_file': mf.get_all_data_as_dict()})



def create_deployment_with_custom_data(wf_name: str, custom_data: dict, compiles: list|None=None):

    mf = deployments.create_deployment(wf_name, custom_data=custom_data, compiles=compiles)
    return http_functions.get_json_response({'status': 'success', 'meta_file': mf.get_all_data_as_dict()})



def start_workflow(request: Request, wf_name: str):
    """
    Starts a workflow. The query parameters are its custom data.
    """

    return create_deployment_with_custom_data(wf_name, {key: value for key, value in request.query_params.items() if key != 'auth-token'})




def start_workflow_post(request: Request, wf_name: str, custom_data: dict = Body(default={})):
    """
    Starts a workflow. The body is its custom data, except `compiles`: the compile list (e.g. of an OBI build list), stored separately.
    """

    custom_data = dict(custom_data)
    compiles = custom_data.pop('compiles', None)

    return create_deployment_with_custom_data(wf_name, custom_data, compiles)



def set_check_error(request: Request, meta_file_id: int, stage_id: int, action_id: int, checked: bool):
    deployments.set_check_error(meta_file_id, stage_id, action_id, checked)
    return http_functions.get_json_response({})



def set_source_ready_4_deployment(request: Request, meta_file_id: int, data: dict = Body(...)):
    """Includes or excludes one object of a deployment. Body: {"lib": ..., "name": ..., "type": ..., "checked": true|false}"""

    if not all(isinstance(data.get(key), str) for key in ['lib', 'name', 'type']):
        raise errors.Invalid_Input_Error("The object needs 'lib', 'name' and 'type'")

    if not isinstance(data.get('checked'), bool):
        raise errors.Invalid_Input_Error("'checked' has to be true or false")

    deployments.set_object_ready(meta_file_id, data['lib'], data['name'], data['type'], data['checked'])
    return http_functions.get_json_response({})



def set_objects_ready(request: Request, meta_file_id: int, data: dict = Body(...)):
    """Includes or excludes several objects of a deployment in one request.

    Body: {"objects": [{"lib": ..., "name": ..., "type": ...}, ...], "ready": true|false}
    Finished objects are left unchanged and listed in the response. If an object doesn't exist, nothing is changed.
    """

    result = deployments.set_objects_ready(meta_file_id, data.get('objects'), data.get('ready'))
    return http_functions.get_json_response({'status': 'success', **result})



def get_objects_table(mf: meta_file.Meta_File) -> dict:
    """Data of the table "Objects to deploy". The page decides nothing: which switch can be used is set here."""

    can_change = mf.status not in [meta_file.Meta_file_status.CANCELED, meta_file.Meta_file_status.FINISHED] \
                 and permission_config.is_user_allowed(current_user.get_user(), permissions.PermissionAction.RUN_WORKFLOW, mf.workflow.name)

    rows = []
    for obj in mf.deploy_objects:
        rows.append({
            'id': obj.id,
            'ready': bool(obj.ready),
            'level': obj.level,
            'prod_lib': obj.prod_lib,
            'lib': obj.lib,
            'name': obj.name,
            'type': obj.type,
            'attribute': obj.attribute,
            'source_only': 'yes' if obj.source_only else 'no',
            'status': obj.deploy_status.value,
            'status_view': get_status_view(obj.deploy_status).__dict__,
            'can_change': can_change and obj.deploy_status != Obj_Status.FINISHED,
        })

    return {'meta_file_id': mf.id, 'can_change': can_change, 'objects': rows}




def get_deployment_objects(request: Request, meta_file_id: int):
    """The rows of the objects table of the deployment page"""

    mf: meta_file.Meta_File = get_deployment(meta_file_id)
    permission_config.check_user_permission(permissions.PermissionAction.READ, mf.workflow.name)

    return http_functions.get_json_response(get_objects_table(mf))



def get_stage_steps_html(request: Request, meta_file_id: int, stage_id: int):
    """Deprecated, until the next major version: GET /show_details/{meta_file_id}/stage/{stage_id} returns the same part of the page"""

    logging.debug(f"Get html for stage steps: {stage_id}, {meta_file_id=}")

    response = show_stage_steps(request, meta_file_id, stage_id)
    return http_functions.get_json_response({'html': response.body.decode()}, status=200)




WATCH_STATE_POLL_INTERVAL_SECONDS = 2


def get_state_signature(meta_file_id: int) -> dict|None:

    mf: meta_file.Meta_File|None = meta_file_data.get_meta_file_by_id(meta_file_id)

    return mf.get_state_signature() if mf else None



def check_watch_permission(meta_file_id: int) -> None:

    # Only the name of the workflow, not the whole deployment (the check is repeated while the stream is open)
    workflow_name = meta_file_data.get_workflow_name(meta_file_id)
    if workflow_name is None:
        raise errors.Not_Found_Error(f"Deployment {meta_file_id} not found")

    permission_config.check_user_permission(permissions.PermissionAction.READ, workflow_name)



def is_watch_allowed(user: str|None, session_id: str|None, meta_file_id: int) -> bool:
    """The stream of the live updates is still allowed: the session hasn't ended (logout, timeout) and the user may read the deployment"""

    if session_id is not None:
        session = server_sessions.load_session_file(session_id)
        if session is None or not session.get('session-data', {}).get('is_logged_in'):
            return False

    current_user.set_user(user)
    try:
        check_watch_permission(meta_file_id)
        return True
    except errors.App_Error:
        return False



async def watch_state(request: Request, meta_file_id: int):
    """Pushes hashes of the deployment state to the web app over SSE, so it knows when to refresh.

    The connection is held open by this single request. Every WATCH_STATE_POLL_INTERVAL_SECONDS the server
    runs a small query and only loads the deployment when something has changed.
    """

    await run_in_threadpool(check_watch_permission, meta_file_id)

    # Checked again while the stream is open (docs/bugfixes/minor-web-defects-2026-11.md, item 8). A request with a token has no session file.
    user = current_user.get_user()
    session = request.state.session
    session_id = None if session.transient else session.session_id


    async def event_stream():

        previous_marker = None
        previous_signature = None
        last_check = time.time()

        try:
            while True:
                if await request.is_disconnected():
                    break

                if time.time() - last_check >= constants.C_WATCH_SESSION_CHECK_SECONDS:
                    last_check = time.time()
                    if not await run_in_threadpool(is_watch_allowed, user, session_id, meta_file_id):
                        # The page connects again and gets 401: "Your session has ended"
                        break

                marker = await run_in_threadpool(meta_file_data.get_state_marker, meta_file_id)

                if marker is None:
                    yield f"data: {json.dumps({'status': 'error', 'message': f'Meta file for ID {meta_file_id} not found'})}\n\n"
                    break

                signature = previous_signature

                if marker != previous_marker:
                    previous_marker = marker
                    signature = await run_in_threadpool(get_state_signature, meta_file_id)

                if signature != previous_signature:
                    previous_signature = signature
                    yield f"data: {json.dumps(signature)}\n\n"
                else:
                    yield ": keep-alive\n\n"

                await asyncio.sleep(WATCH_STATE_POLL_INTERVAL_SECONDS)
        except Exception as e:
            logging.exception(e, stack_info=True)
            yield f"data: {json.dumps({'status': 'error', 'message': 'The state of the deployment could not be read'})}\n\n"

    return StreamingResponse(event_stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})




def get_workflows(request: Request):
    return http_functions.get_json_response(get_readable_workflows())




def get_project_counts() -> dict:
    """Projects the user may read -> {status: number of deployments}"""

    result = {}

    for project in dict.fromkeys(wf['default_project'] for wf in get_readable_workflows()):
        result[project] = {}
        for depl in get_readable_deployments(deploy_version.Deploy_Version.get_deployments(project)['deployments']):
            if depl['status'] not in result[project]:
                result[project][depl['status']] = 0
            result[project][depl['status']] = result[project][depl['status']] + 1

    return result



def get_projects(request: Request):
    return http_functions.get_json_response(get_project_counts())




def show_permissions(request: Request):
    """The permissions page (docs/features/web-ui-permissions-page.md)"""

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)

    return http_functions.get_html_response(request, 'admin/permissions.html', sidebar=get_sidebar_data(request),
                                            state=permission_config.get_state(), current=(current_user.get_user() or '').lower())



def get_permissions(request: Request):
    """Users, roles, their permissions and the version of the permissions, for a change with `version`"""

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)

    return http_functions.get_json_response(permission_config.get_state())



def add_permission(request: Request, data: dict = Body(...)):
    """Adds a user or a role. With `version`: only if the permissions haven't changed since (409 otherwise)."""

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)
    two_factor.require_recent_code(request)

    type = data.get('type')
    general = data.get('general', [])
    roles: List[str] = data.get('roles', [])

    if type not in ('user', 'role'):
        raise errors.Invalid_Input_Error(f"Unknown permission type '{type}'")
    if not isinstance(general, list):
        raise errors.Invalid_Input_Error("'general' has to be a list")

    try:
        general_actions = [permissions.PermissionAction(action) for action in general]
    except ValueError as e:
        raise errors.Invalid_Input_Error(str(e)) from e

    logging.debug(f"Add permission of type {type} with name {data.get('name')} for roles {roles}, {general=}")

    with permission_config.change_lock():
        permission_config.PermissionKonfig.check_reload(force=True)
        permission_config.check_version(data.get('version'))

        if type == 'user':
            name = permission_config.check_name(data.get('name'), list(permission_config.PermissionKonfig.user_permissions), 'user')
            permission_config.PermissionKonfig.add_user_permission(name=name, general=general_actions)
        else:
            name = permission_config.check_name(data.get('name'), list(permission_config.PermissionKonfig.role_permissions), 'role')
            permission_config.PermissionKonfig.add_role_permission(name=name, general=general_actions)

        version = permission_config.get_version()

    audit.record(request, 'permissions_changed', object=f"{type} {name.lower()}", details={'new': True, 'added': sorted(f"general: {a.value}" for a in general_actions)})

    return http_functions.get_json_response({"status": "success", "name": name.lower(), "version": version})



def save_permissions(request: Request, data: dict = Body(...)):
    """
    Changes users and roles. Users and roles which are not sent stay unchanged; deleted only with `deleted_users` / `deleted_roles`.
    With `version`: only if the permissions haven't changed since (409 otherwise). Nothing is changed if afterwards
    no user would have `admin` (409).
    """

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)
    two_factor.require_recent_code(request)

    # Users and roles which are missing in the request are kept: the web app reads them from its page,
    # and an error there must not delete them. They are only deleted if the request says so.
    user_permissions = data.get('user_permissions', {})
    role_permissions = data.get('role_permissions', {})
    deleted_users = data.get('deleted_users', [])
    deleted_roles = data.get('deleted_roles', [])
    version = data.get('version')

    if not all(isinstance(value, dict) for value in [user_permissions, role_permissions]) or not all(isinstance(value, list) for value in [deleted_users, deleted_roles]):
        raise errors.Invalid_Input_Error("user_permissions and role_permissions have to be objects, deleted_users and deleted_roles lists")
    if version is not None and not isinstance(version, str):
        raise errors.Invalid_Input_Error("'version' has to be a string")

    with permission_config.change_lock():
        konfig = permission_config.PermissionKonfig
        konfig.check_reload(force=True)
        permission_config.check_version(version)

        # Changed on copies: nothing changes if a check fails
        users = copy.deepcopy(konfig.user_permissions)
        roles = copy.deepcopy(konfig.role_permissions)
        users_before, roles_before = copy.deepcopy(users), copy.deepcopy(roles)

        unknown_users = user_permissions.keys() - users.keys()
        unknown_roles = role_permissions.keys() - roles.keys()
        if unknown_users or unknown_roles:
            raise errors.Invalid_Input_Error(f"Unknown users or roles: {', '.join(sorted(unknown_users | unknown_roles))}")

        for user in deleted_users:
            user_permissions.pop(user, None)
            users.pop(user, None)

        for role in deleted_roles:
            role_permissions.pop(role, None)
            roles.pop(role, None)
            for user in users.values():
                user.roles = [r for r in user.roles if r != role]

        try:
            sent_infos = {user: (value or {}).get('detailed_infos') for user, value in user_permissions.items()}
            konfig.convert_permissions('user', user_permissions)
            konfig.convert_permissions('role', role_permissions)
        except (ValueError, AttributeError, TypeError) as e:
            raise errors.Invalid_Input_Error(f"Invalid permissions: {e}") from e

        for user, perm in user_permissions.items():
            users[user].permissions.general = perm.permissions.general
            users[user].permissions.workflows = perm.permissions.workflows
            users[user].roles = perm.roles
            if sent_infos.get(user) is not None:
                users[user].detailed_infos.description = perm.detailed_infos.description
                users[user].detailed_infos.mail = perm.detailed_infos.mail

        for role, perm in role_permissions.items():
            roles[role].permissions.general = perm.permissions.general
            roles[role].permissions.workflows = perm.permissions.workflows

        missing_roles = sorted({role for user in users.values() for role in user.roles if role not in roles})
        if missing_roles:
            raise errors.Invalid_Input_Error(f"Unknown roles: {', '.join(missing_roles)}")

        if not permission_config.has_admin(users, roles):
            raise errors.Conflict_Error("After this change no user would have the permission admin")

        konfig.user_permissions = users
        konfig.role_permissions = roles
        konfig.allowed_users = list(users.keys())
        konfig.save_permissions()
        new_version = permission_config.get_version()

    # What has changed, for each user and role (docs/features/audit-log.md)
    changes = {**{f"user {name}": change for name, change in audit.get_changes(users_before, users).items()},
               **{f"role {name}": change for name, change in audit.get_changes(roles_before, roles).items()}}
    for name, change in changes.items():
        audit.record(request, 'permissions_changed', object=name, details=change)

    # A user of the same name later must not get the token or the second factor of the removed one (docs/bugfixes/api-token-outlives-user.md)
    for user in deleted_users:
        if app_login.drop_token_of(user):
            logging.warning(f"API token of the removed user {user} deleted")
        if user_mfa_data.remove(user):
            logging.warning(f"Two-factor authentication of the removed user {user} deleted")

    return http_functions.get_json_response({"status": "success", "version": new_version})
