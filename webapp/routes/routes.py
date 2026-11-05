import asyncio
import logging, os, json
from typing import List
from pathlib import Path

from fastapi import Body, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse, StreamingResponse

# Custom modules
import etc.global_cfg as global_cfg
from etc import constants

from modules import action_type, current_user, errors, files, permissions, version
from modules import deploy_version, meta_file
from modules import workflow, processing_service
from modules.db import meta_file_data, meta_file_history_data, processing_user_data, run_history_data, deploy_object_data, processing_job_data
from modules.deploy_object import Deploy_Object

from web_modules import http_functions
from web_modules import flowchart, app_login
from modules import permission_config
from modules.object_status import Status as Obj_Status


# Handlers which only do blocking work are plain functions, so they run in a thread of FastAPI.
# Errors are not handled here: WebMiddleware.get_error_response creates the response.



def get_deployment(meta_file_id: int) -> meta_file.Meta_File:

    mf: meta_file.Meta_File|None = meta_file_data.get_meta_file_by_id(meta_file_id)

    if mf is None:
        raise errors.Not_Found_Error(f"Deployment {meta_file_id} not found")

    return mf



def get_stage(mf: meta_file.Meta_File, stage_id: int):

    stage = mf.get_stage_by_id(stage_id)

    if stage is None:
        raise errors.Not_Found_Error(f"Stage {stage_id} not found in deployment {mf.id}")

    return stage



def check_read_permission(meta_file_id: int|None) -> None:
    """For data of a deployment which is requested without loading the deployment"""

    if meta_file_id is None:
        raise errors.Not_Found_Error("Not found")

    permission_config.check_user_permission(permissions.PermissionAction.READ, meta_file_data.get_workflow_name(meta_file_id))



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



def get_sidebar_data(request: Request):
    x ={}

    session = request.state.session

    x['projects'] = list(dict.fromkeys(wf['default_project'] for wf in get_readable_workflows()))
    current_user = session.get('current_user', None)
    x['current_user'] = current_user.upper() if current_user is not None else None
    x['logs'] = os.listdir('log/') if is_admin() else []
    x['active'] = request.query_params.get('sidebar_active', 'deployments')
    x['app_version'] = version.APP_VERSION
    logging.debug(f"Sidebar: {x}")

    return x




def index(request: Request):

    session = request.state.session

    project= session.get('current_project', None) or global_cfg.C_DEFAULT_PROJECT

    dv = get_readable_deployments(deploy_version.Deploy_Version.get_deployments(project)['deployments'])

    deployments: list = []
    for d in dv:
        deployments.append({
            'version': d.get('version', None),
            'status': d.get('status', None),
            'workflow': d.get('workflow_name', None),
            'create_time': str(d.get('create_time', None)).split('.')[0] if d.get('create_time', None) is not None else None,
            'update_time': str(d.get('update_time', None)).split('.')[0] if d.get('update_time', None) is not None else None,
            'meta_file_id': d.get('meta_file_id', None)
        })

    logging.debug("Send response")

    #current_user=session['current_user'],
    return http_functions.get_html_response(request,
                                'overview/list-deployments.html',
                                project=project,
                                sidebar=get_sidebar_data(request),
                                deployment_details=dv,
                                deployments=deployments)





def list_objects(request: Request):

    do = deploy_object_data.get_deploy_object_list(filters={}, workflows=get_readable_workflow_names())

    logging.debug(f"List objects. {len(do)} objects found.")

    #current_user=session['current_user'],
    return http_functions.get_html_response(request,
                                'overview/list-objects.html',
                                sidebar=get_sidebar_data(request),
                                deployment_objects=do)




def deploy_object_lifecycle(request: Request, project: str, prod_lib: str, name: str, type: str, attribute: str):
    logging.debug(f"Get deploy object lifecycle for {project=}, {prod_lib=}, {name=}, {type=}, {attribute=}")

    do = deploy_object_data.get_deploy_object_lifecycle(project, prod_lib, name, type, attribute, workflows=get_readable_workflow_names())

    if do is None:
        raise errors.Not_Found_Error(f"Deploy object not found for project '{project}', lib '{prod_lib}', name '{name}', type '{type}', attribute '{attribute}'")

    return http_functions.get_json_response(do)



def list_deployments(request: Request, project: str):
    return http_functions.get_json_response(get_readable_deployments(deploy_version.Deploy_Version.get_deployment_list(project)))



def select_project(request: Request, project: str):

    available_projects = get_sidebar_data(request)['projects']
    if (project not in available_projects):
        logging.error(f"Project '{project}' is not in list of {available_projects}.")
        project = available_projects[0] if len(available_projects) > 0 else None

    session = request.state.session
    session['current_project'] = project

    return RedirectResponse('/', status_code=302)



def show_log(request: Request, log: str, number_of_lines: int=100):

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)

    logging.debug(f"Read log file {log=}")

    if log not in os.listdir('log/'):
        raise errors.Not_Found_Error(f"Log {log} not found")

    data = []
    file = files.readFile(f"log/{log}").splitlines()
    data = file[-number_of_lines:]
    logging.debug(f"reverse data")
    data = list(reversed(data))

    logging.debug("Send response")
    return http_functions.get_html_response(request, 'admin/log.html', sidebar=get_sidebar_data(request), logfile=log, content=data, number_of_lines=number_of_lines)



async def login(request: Request):
    session = request.state.session
    if session.get('is_logged_in', False):
        return RedirectResponse("/", status_code=302)
    return http_functions.get_html_response(request, 'login.html', sidebar=None, error_text=session.get('error_text', None))



def show_user(request: Request):

    session = request.state.session
    user_keys=app_login.get_user_keys()
    user_key = user_keys.get(session['current_user'], None)

    return http_functions.get_html_response(request, 'admin/user.html', sidebar=get_sidebar_data(request), user_key=user_key)



def generate_user_key(request: Request):
    session = request.state.session
    logging.debug(f"Set new key for user {session['current_user']}")

    return http_functions.get_json_response({"token": app_login.generate_new_user_key(request)})



def drop_user_key(request: Request):
    session = request.state.session
    logging.debug(f"Drop key for user {session['current_user']}")

    app_login.drop_user_key(request)
    return http_functions.get_json_response({})



def logout(request: Request):

    if hasattr(request.state, 'session'):
        logging.debug(f"Logout user {request.state.session.get('current_user', None)}")
        request.state.session.destroy()

    return RedirectResponse("/login", status_code=302)



def show_workflows(request: Request):

    logging.debug('Call workflows')

    wf = get_readable_workflows()
    wf_json = json.dumps(wf, default=str, indent=4)
    invalid_files = workflow.Workflow.get_invalid_workflow_files() if is_admin() else {}

    logging.debug("Send response")
    return http_functions.get_html_response(request, 'admin/workflows.html', sidebar=get_sidebar_data(request), workflows=wf, workflow_json=wf_json, projects=list(dict.fromkeys(w['default_project'] for w in wf)), invalid_files=invalid_files)



# Newest jobs of the processing service which are listed in the settings
SETTINGS_NUMBER_OF_JOBS = 30


def show_settings(request: Request):

    logging.debug('Call settings')

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)

    keys=app_login.get_user_keys()

    logging.debug("Send response")
    return http_functions.get_html_response(request, 'admin/settings.html',
        sidebar=get_sidebar_data(request),
        permission_actions=permissions.PermissionAction,
        allowed_users=permission_config.PermissionKonfig.get_user_list(),
        user_permissions=permission_config.PermissionKonfig.user_permissions,
        role_permissions=permission_config.PermissionKonfig.role_permissions,
        default_project=global_cfg.C_DEFAULT_PROJECT,
        workflows=workflow.Workflow.get_all_workflows_json(),
        port='????',
        path=Path(os.path.dirname(__file__)),
        keys=keys,
        processing_mode=constants.C_PROCESSING_MODE,
        processing_service_running=processing_service.notify(),
        processing_jobs=[job.get_dict() for job in reversed(processing_job_data.get_jobs(limit=SETTINGS_NUMBER_OF_JOBS))]
        )



def show_details(request: Request, project: str, version: int):

    meta: meta_file.Meta_File = deploy_version.Deploy_Version.get_deployment(project, version)

    return show_details_by_id(request, meta.id)



def show_details_by_id(request: Request, meta_file_id: int):
    logging.debug(f'Show details of {meta_file_id=}')

    mf: meta_file.Meta_File = get_deployment(meta_file_id)
    permission_config.check_user_permission(permissions.PermissionAction.READ, mf.workflow.name)

    flow = flowchart.get_flowchar_html(request, mf)
    mf_dict = mf.get_all_data_as_dict()

    mf_json = json.dumps(mf_dict, default=str, indent=4)
    progress = (len(mf.workflow.stages) - len(mf.get_open_stages())) / len(mf.workflow.stages)
    progress = progress * 100
    editable_custom_fields = mf.get_editable_custom_fields()
    can_edit_custom_data = len(editable_custom_fields) > 0 and permission_config.is_user_allowed(current_user.get_user(), permissions.PermissionAction.EDIT_CUSTOM_DATA, mf.workflow.name)

    return http_functions.get_html_response(request, 'overview/show-deployment.html', sidebar=get_sidebar_data(request), progress=progress, deployment_json=mf_json, deployment_dict=mf_dict, error='', flow_html=flow['html'], flow_javascript=flow['java_script'], editable_custom_fields=editable_custom_fields, can_edit_custom_data=can_edit_custom_data)



def run_stage(request: Request, meta_file_id: int, stage_id: int, option: str):

    logging.debug(f"Run stage-id {stage_id} of meta_file_id {meta_file_id} with option {option=}")

    if option not in ['continue', 'run_all']:
        raise errors.Invalid_Input_Error(f"Option '{option}' is invalid. Valid options are: 'continue', 'run_all'")

    mf: meta_file.Meta_File = get_deployment(meta_file_id)
    permission_config.check_user_permission(permissions.PermissionAction.RUN_WORKFLOW, mf.workflow.name, stage=get_stage(mf, stage_id).name)

    result = {'status': 'success'}
    result.update(mf.start_stage(stage_id, continue_run=option != 'run_all'))

    return http_functions.get_json_response(result)




def get_meta_file_json(request: Request, meta_file_id: int):
    logging.debug(f"Get meta file from: {meta_file_id=}")

    mf: meta_file.Meta_File = get_deployment(meta_file_id)
    permission_config.check_user_permission(permissions.PermissionAction.READ, mf.workflow.name)

    return http_functions.get_json_response(mf.get_all_data_as_dict())



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
    logging.debug(f"Get processing history from: {meta_file_id=}")

    check_read_permission(meta_file_id)

    pud: list = processing_user_data.get_processing_user_by_meta_id(meta_file_id)

    return http_functions.get_json_response(pud)



def cancel_deployment(request: Request, meta_file_id: int):

    logging.debug(f"Cancel Deployment: {meta_file_id=}")
    mf: meta_file.Meta_File = get_deployment(meta_file_id)

    permission_config.check_user_permission(permissions.PermissionAction.CANCEL_WORKFLOW, mf.workflow.name)
    processing_user_data.create_action_log(action=action_type.Action_type.CANCEL_WF, meta_file=mf)

    mf.cancel_deployment()
    # A stage which is already running is not stopped. Like without the processing service.
    processing_job_data.cancel_queued_jobs(mf.id)

    return http_functions.get_json_response({'status': 'success'})



def cancel_job(request: Request, job_id: int):
    """Removes a stage run from the queue of the processing service, as long as it has not been started."""

    logging.debug(f"Cancel processing job: {job_id=}")

    job = processing_job_data.get_job(job_id)
    if job is None:
        raise errors.Not_Found_Error(f"Processing job {job_id} not found")

    mf: meta_file.Meta_File = get_deployment(job.meta_file_id)
    permission_config.check_user_permission(permissions.PermissionAction.RUN_WORKFLOW, mf.workflow.name, stage=get_stage(mf, job.stage_id).name)

    if not processing_job_data.cancel_job(job_id):
        raise errors.Conflict_Error(f"Processing job {job_id} is not in the queue anymore.")

    return http_functions.get_json_response({'status': 'success'})



def edit_custom_data(request: Request, meta_file_id: int, data: dict = Body(...)):
    """
    Changes the editable fields of the custom data of a deployment.
    Body: {"fields": {"{JSONPath}": value, ...}}
    Only fields defined in `editable_fields` of the workflow can be changed.
    """

    fields = data.get('fields')
    if not isinstance(fields, dict) or len(fields) == 0:
        raise errors.Invalid_Input_Error("No fields to change provided!")

    logging.debug(f"Edit custom data: {meta_file_id=}, {fields=}")
    mf: meta_file.Meta_File = get_deployment(meta_file_id)

    permission_config.check_user_permission(permissions.PermissionAction.EDIT_CUSTOM_DATA, mf.workflow.name)

    changed = mf.update_custom_data(fields)
    processing_user_data.create_action_log(action=action_type.Action_type.EDIT_CUSTOM_DATA, details=f"Changed custom data: {', '.join(changed)}", meta_file=mf)

    return http_functions.get_json_response({'status': 'success'})



def reset_stage_status(request: Request, meta_file_id: int, stage_id: int):

    logging.debug(f"Reset Stage Status: {meta_file_id=}, {stage_id=}")
    mf: meta_file.Meta_File = get_deployment(meta_file_id)
    stage = get_stage(mf, stage_id)

    permission_config.check_user_permission(permissions.PermissionAction.RUN_WORKFLOW, mf.workflow.name, stage=stage.name)

    mf.reset_stage(stage)
    processing_user_data.create_action_log(action=action_type.Action_type.RESET_STAGE_STATUS, meta_file=mf)

    return http_functions.get_json_response({'status': 'success'})



def reset_last_finished_stage(request: Request, meta_file_id: int, stage_id: int):
    """Sets the stage which has been finished last back to 'ready', so it can be run again.
    Only possible as long as the deployment is not finished and no stage is in process.
    """

    logging.debug(f"Reset last finished stage: {meta_file_id=}, {stage_id=}")
    mf: meta_file.Meta_File = get_deployment(meta_file_id)

    permission_config.check_user_permission(permissions.PermissionAction.RUN_WORKFLOW, mf.workflow.name, stage=get_stage(mf, stage_id).name)

    stage = mf.reset_last_finished_stage(stage_id)
    processing_user_data.create_action_log(action=action_type.Action_type.RESET_LAST_FINISHED_STAGE, details=f"Reset finished stage to '{stage.status.value}'", meta_file=mf, stage=stage)

    return http_functions.get_json_response({'status': 'success'})



def reset_deployment_status(request: Request, meta_file_id: int):

    logging.debug(f"Reset Deployment Status: {meta_file_id=}")

    mf: meta_file.Meta_File = get_deployment(meta_file_id)

    permission_config.check_user_permission(permissions.PermissionAction.RUN_WORKFLOW, mf.workflow.name)

    mf.reset_status()
    processing_user_data.create_action_log(action=action_type.Action_type.RESET_DEPLOYMENT_STATUS, meta_file=mf)

    return http_functions.get_json_response({'status': 'success'})



def create_deployment(request: Request, wf_name: str, commit: str|None=None, obj_list: str|None=None):
    """
    Creates a new deployment for a given workflow, commit, and the name of the list of objects.
    This function checks if a deployment already exists for the specified commit and workflow.
    If a deployment exists and its status is not 'CANCELED', it returns an error response.
    Otherwise, it creates a new meta file for the deployment, sets its status to 'READY', and returns the deployment metadata.
    Args:
        wf_name (str): The name of the workflow for which the deployment is to be created.
        commit (str): The commit hash or identifier associated with the deployment.
        obj_list (str): Path of a file with the objects to be included in the deployment (see docs/workflow.md#object-list).

    Returns:
        A JSON response containing the status of the operation and relevant data or error message.
    """

    logging.debug(f"Create Deployment: {wf_name=}, {commit=}, {obj_list=}")

    permission_config.check_user_permission(permissions.PermissionAction.START_WORKFLOW, wf_name)

    wf = workflow.Workflow(wf_name)
    logging.debug(f"Workflow: {wf}")
    existing_version = deploy_version.Deploy_Version.get_deployment_by_commit(project=wf.default_project, commit=commit)

    logging.debug(f"{existing_version=}, {meta_file.Meta_file_status.CANCELED=}")

    if existing_version is not None and meta_file.Meta_file_status(existing_version['status']) != meta_file.Meta_file_status.CANCELED:
        raise errors.Conflict_Error(f"Given commit is already used in deployment version {existing_version['version']} with status '{existing_version['status']}'")

    mf: meta_file.Meta_File = meta_file_data.create_new_meta_file(workflow_name=wf_name, object_list=obj_list)
    #mf = meta_file.Meta_File(workflow_name=wf_name, object_list=obj_list)
    processing_user_data.create_action_log(action=action_type.Action_type.CREATE_WF, details=wf_name, meta_file=mf)

    mf.commit = commit
    mf.set_status(meta_file.Meta_file_status.READY)

    return http_functions.get_json_response({'status': 'success', 'meta_file': mf.get_all_data_as_dict()})





def create_deployment_with_custom_data(wf_name: str, custom_data: dict, compiles: list|None=None):

    logging.info(f"Starting workflow {wf_name} with {len(custom_data)} custom data fields{'' if compiles is None else ' and a compile list'}")

    permission_config.check_user_permission(permissions.PermissionAction.START_WORKFLOW, wf_name)

    mf = meta_file_data.create_new_meta_file(workflow_name=wf_name, custom_data=custom_data, compiles=compiles)
    processing_user_data.create_action_log(action=action_type.Action_type.CREATE_WF, details=wf_name, meta_file=mf)

    mf.set_status(meta_file.Meta_file_status.READY)

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
    logging.debug(f"Set check error action_id: {action_id}, checked: {checked}")
    session = request.state.session

    mf: meta_file.Meta_File = get_deployment(meta_file_id)
    if mf.status in [meta_file.Meta_file_status.CANCELED, meta_file.Meta_file_status.FINISHED]:
        raise errors.Conflict_Error(f"Can't change step check because deployment is already {mf.status.value}.")

    mf.set_action_check(stage_id, action_id, checked, session['current_user'])

    return http_functions.get_json_response({})




def set_source_ready_4_deployment(request: Request, meta_file_id: int, data: dict = Body(...)):
    logging.debug(f"Set source ready for deployment lib: {data['lib']}, name: {data['name']}, type: {data['type']}, checked: {data['checked']}, {meta_file_id=}")

    mf: meta_file.Meta_File = get_deployment(meta_file_id)

    permission_config.check_user_permission(permissions.PermissionAction.RUN_WORKFLOW, mf.workflow.name)

    if mf.status in [meta_file.Meta_file_status.CANCELED, meta_file.Meta_file_status.FINISHED]:
        raise errors.Conflict_Error(f"Can't change object status because deployment is already in status '{mf.status.value}'.")

    obj: Deploy_Object = mf.deploy_objects.get_deploy_object(lib=data['lib'], name=data['name'], type=data['type'])

    if obj is None:
        raise errors.Not_Found_Error(f"Object {data['lib']}/{data['name']}({data['type']}) not found")

    if obj.deploy_status == Obj_Status.FINISHED:
        raise errors.Conflict_Error(f"Can't change object status because object is already in status '{obj.deploy_status.value}'.")

    processing_user_data.create_action_log(action=action_type.Action_type.CHANGE_OBJ_READY_STATUS, details=f"Set object {data['lib']}/{data['name']}({data['type']}) ready={data['checked']}", meta_file=mf)

    obj.ready = data['checked']
    mf.save()

    return http_functions.get_json_response({})




def get_stage_steps_html(request: Request, meta_file_id: int, stage_id: int):

    logging.debug(f"Get html for stage steps: {stage_id}, {meta_file_id=}")

    mf_obj: meta_file.Meta_File = get_deployment(meta_file_id)
    permission_config.check_user_permission(permissions.PermissionAction.READ, mf_obj.workflow.name)

    html = flowchart.generate_stage_steps_html(request, mf_obj, get_stage(mf_obj, stage_id))
    return http_functions.get_json_response({'html': html}, status=200)




WATCH_STATE_POLL_INTERVAL_SECONDS = 2


def get_state_signature(meta_file_id: int) -> dict|None:

    mf: meta_file.Meta_File|None = meta_file_data.get_meta_file_by_id(meta_file_id)

    return mf.get_state_signature() if mf else None



def check_watch_permission(meta_file_id: int) -> None:

    mf = get_deployment(meta_file_id)
    permission_config.check_user_permission(permissions.PermissionAction.READ, mf.workflow.name)



async def watch_state(request: Request, meta_file_id: int):
    """Pushes hashes of the deployment state to the web app over SSE, so it knows when to refresh.

    The connection is held open by this single request. Every WATCH_STATE_POLL_INTERVAL_SECONDS the server
    runs a small query and only loads the deployment when something has changed.
    """

    await run_in_threadpool(check_watch_permission, meta_file_id)


    async def event_stream():

        previous_marker = None
        previous_signature = None

        try:
            while True:
                if await request.is_disconnected():
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




def get_projects(request: Request):

    result = {}

    for project in dict.fromkeys(wf['default_project'] for wf in get_readable_workflows()):
        result[project] = {}
        for depl in get_readable_deployments(deploy_version.Deploy_Version.get_deployments(project)['deployments']):
            if depl['status'] not in result[project]:
                result[project][depl['status']] = 0
            result[project][depl['status']] = result[project][depl['status']] + 1

    return http_functions.get_json_response(result)




def add_permission(request: Request, data: dict = Body(...)):
    type: str = data['type']
    name: str = data['name']
    roles: List[str] = data.get('roles', [])
    general: List[str] = data['general']

    logging.debug(f"Add permission of type {type} with name {name} for roles {roles}, {general=}")

    permission_execution = {
        'user': permission_config.PermissionKonfig.add_user_permission,
        'role': permission_config.PermissionKonfig.add_role_permission
    }

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)

    if type not in permission_execution:
        raise errors.Invalid_Input_Error(f"Unknown permission type '{type}'")

    try:
        general_actions = [permissions.PermissionAction(action) for action in general]
    except ValueError as e:
        raise errors.Invalid_Input_Error(str(e))

    permission_execution[type](name=name, general=general_actions)

    return http_functions.get_json_response({"status": "success"})



def save_permissions(request: Request, data: dict = Body(...)):

    permission_config.check_user_permission(permissions.PermissionAction.ADMIN)

    # Handle user permissions
    user_permissions = data.get('user_permissions', {})

    users_to_delete = permission_config.PermissionKonfig.user_permissions.keys() - user_permissions.keys()
    for user in users_to_delete:
        del permission_config.PermissionKonfig.user_permissions[user]

    permission_config.PermissionKonfig.convert_permissions('user', user_permissions)
    for user, perm in user_permissions.items():
        permission_config.PermissionKonfig.user_permissions[user].permissions.general = perm.permissions.general
        permission_config.PermissionKonfig.user_permissions[user].permissions.workflows = perm.permissions.workflows
        permission_config.PermissionKonfig.user_permissions[user].roles = perm.roles

    # Handle role permissions
    role_permissions = data.get('role_permissions', {})

    roles_to_delete = permission_config.PermissionKonfig.role_permissions.keys() - role_permissions.keys()
    for role in roles_to_delete:
        del permission_config.PermissionKonfig.role_permissions[role]

    permission_config.PermissionKonfig.convert_permissions('role', role_permissions)
    for role, perm in role_permissions.items():
        permission_config.PermissionKonfig.role_permissions[role].permissions.general = perm.permissions.general

    permission_config.PermissionKonfig.save_permissions()

    return http_functions.get_json_response({"status": "success"})
