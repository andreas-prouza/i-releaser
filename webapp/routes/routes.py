import logging, sys, os, json
from typing import List
from pathlib import Path

from fastapi import Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse

# Custom modules
import etc.constants as constants
import etc.global_cfg as global_cfg

from modules import action_type, files, permissions, stage_status
from modules import deploy_version, meta_file
from modules import workflow
from modules.db import meta_file_data, meta_file_history_data, processing_user_data, run_history_data
from modules.deploy_object import Deploy_Object

from web_modules import http_functions
from web_modules import flowchart, app_login
from modules import permission_config





def get_sidebar_data(request: Request):
    x ={}

    session = request.state.session

    x['projects'] = workflow.Workflow.get_all_projects()
    current_user = session.get('current_user', None)
    x['current_user'] = current_user.upper() if current_user is not None else None
    x['logs'] = os.listdir('log/')
    x['active'] = request.query_params.get('sidebar_active', 'deployments')
    logging.debug(f"Sidebar: {x}")

    return x




async def index(request: Request):
    
    logging.debug(sys.path)
    logging.debug('Call index.html')
    session = request.state.session

    project= session.get('current_project', None) or global_cfg.C_DEFAULT_PROJECT

    dv = deploy_version.Deploy_Version.get_deployments(project)

    deployments: list = []
    for d in dv['deployments']:
        deployments.append({
            'version': d.get('version', None),
            'status': d.get('status', None),
            'workflow': d.get('workflow_name', None),
            'create_time': str(d.get('create_time', None)).split('.')[0] if d.get('create_time', None) is not None else None,
            'update_time': str(d.get('update_time', None)).split('.')[0] if d.get('update_time', None) is not None else None,
            'meta_file_id': d.get('meta_file_id', None)
        })

    logging.debug(f"Deployments: {deployments=}")

    logging.debug("Send response")
    
    #current_user=session['current_user'], 
    return http_functions.get_html_response(request, 
                                'overview/list-deployments.html', 
                                project=project, 
                                sidebar=get_sidebar_data(request), 
                                deployment_details=dv['deployments'],
                                deployments=deployments) 




async def list_deployments(request: Request, project: str):
    dv = deploy_version.Deploy_Version.get_deployments(project)
    logging.debug(dv)
    dv = dv['deployments']
    return JSONResponse(content=dv)



async def select_project(request: Request, project: str):

    available_projects = workflow.Workflow.get_all_projects()
    if (project not in available_projects):
        logging.error(f"Project '{project}' is not in list of {available_projects}.")
        project = available_projects[0]
    
    session = request.state.session
    session['current_project'] = project

    return RedirectResponse('/', status_code=302)



async def show_log(request: Request, log: str, number_of_lines: int=100):

    logging.debug(f"Read log file {log=}")

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



async def show_user(request: Request):

    session = request.state.session
    user_keys=app_login.get_user_keys()
    user_key = user_keys.get(session['current_user'], None)

    return http_functions.get_html_response(request, 'admin/user.html', sidebar=get_sidebar_data(request), user_key=user_key) 



async def generate_user_key(request: Request):
    session = request.state.session
    logging.debug(f"Set new key for user {session['current_user']}")

    app_login.generate_new_user_key(request)
    return http_functions.get_json_response({"token": app_login.generate_new_user_key(request)})
    


async def drop_user_key(request: Request):
    session = request.state.session
    logging.debug(f"Drop key for user {session['current_user']}")

    app_login.drop_user_key(request)
    return http_functions.get_json_response({})
    


async def logout(request: Request):

    logging.debug(f"{request.state=}")
    logging.debug(f"{request.state.session=}")
    if request.state is not None and hasattr(request.state, 'session'):
        logging.debug(f"Logout user {request.state.session.get('current_user', None)}")
        session = request.state.session
        session.pop('error_text', None)
        session.pop('is_logged_in', None)
        session.pop('uid', None)
        session['__invalid__'] = True
        session.save()

    return RedirectResponse("/login", status_code=302)



async def show_workflows(request: Request):

    logging.debug('Call workflows')

    wf = workflow.Workflow.get_all_workflows_json()
    wf_json = json.dumps(wf, default=str, indent=4)

    logging.debug("Send response")
    return http_functions.get_html_response(request, 'admin/workflows.html', sidebar=get_sidebar_data(request), workflows=wf, workflow_json=wf_json, projects=workflow.Workflow.get_all_projects()) 



async def show_settings(request: Request):

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
        port='????',
        path=Path(os.path.dirname(__file__)),
        keys=keys
        )



async def show_details(request: Request, meta_file_id: int):
    logging.debug(f'Show details of {meta_file_id=}')
    logging.debug(request.form)

    error = ''
    mf_dict = None
    mf_json = None

    try:
        mf: meta_file.Meta_File = meta_file_data.get_meta_file_by_id(meta_file_id)
        permission_config.check_user_permission(permissions.PermissionAction.READ, mf.workflow.name)

        flow = flowchart.get_flowchar_html(request, mf)
        mf_dict = mf.get_all_data_as_dict()
        mf_json = json.dumps(mf_dict, default=str, indent=4)
        progress = (len(mf.workflow.stages) - len(mf.get_open_stages())) / len(mf.workflow.stages)
        progress = progress * 100
        return http_functions.get_html_response(request, 'overview/show-deployment.html', sidebar=get_sidebar_data(request), progress=progress, deployment_json=mf_json, deployment_dict=mf_dict, error=error, flow_html=flow['html'], flow_javascript=flow['java_script']) 

    except Exception as e:
        logging.debug(f"{os.getcwd()=}")
        logging.exception(e, stack_info=True)
        error = e
        return http_functions.get_html_response(request, 'error.html', sidebar=get_sidebar_data(request), error=error)



async def run_stage(request: Request, meta_file_id: int, stage_id: int, option: str) -> JSONResponse:
    result={'status': 'success'}
    status=200
    logging.debug(f"Run stage-id {stage_id} of meta_file_id {meta_file_id} with option {option=}")
    session = request.state.session

    mf: meta_file.Meta_File = meta_file_data.get_meta_file_by_id(meta_file_id)
    permission_config.check_user_permission(permissions.PermissionAction.RUN_WORKFLOW, mf.workflow.name, stage=mf.get_stage_by_id(stage_id).name)

    try:
        
        mf.set_status(meta_file.Meta_file_status.READY)

        continue_run = True
        if option == 'run_all':
            continue_run = False

        mf.run_current_stage_as_thread(stage_id, continue_run=continue_run)

    except Exception as e:
        logging.error("An error occured. Please check details!")
        logging.exception(e, stack_info=True)
        return http_functions.get_json_response_error(str(e))

    return http_functions.get_json_response(result, status=status)




async def get_meta_file_json(request: Request, meta_file_id: int):
    logging.debug(f"Get meta file from: {meta_file_id=}")

    mf: meta_file.Meta_File = meta_file_data.get_meta_file_by_id(meta_file_id)
    permission_config.check_user_permission(permissions.PermissionAction.READ, mf.workflow.name)

    if not mf:
        return http_functions.get_json_response_error(f"Meta file for ID {meta_file_id} not found", status=404)


    #mf_json = json.dumps(meta_file_json, default=str, indent=4)

    return http_functions.get_json_response(mf.get_all_data_as_dict())
    


async def get_activity_log(request: Request, id: int):
    
    logging.debug(f"Get logs from: {id=}")
    
    history = meta_file_history_data.get_run_history_by_id(id)
    if history:
        return http_functions.get_json_response(history.get_dict())

    return http_functions.get_json_response({})
    



async def get_action_log(request: Request, id: int):
    
    logging.debug(f"Get logs from: {id=}")
    
    history = run_history_data.get_run_history_by_id(id)
    if history:
        return http_functions.get_json_response(history.get_dict())

    return http_functions.get_json_response({})
    



async def show_processing_history(request: Request, meta_file_id: int):
    logging.debug(f"Get processing history from: {meta_file_id=}")

    pud: list = processing_user_data.get_processing_user_by_meta_id(meta_file_id)

    return http_functions.get_json_response(pud)



async def cancel_deployment(request: Request, meta_file_id: int):

    try:
        logging.debug(f"Cancel Deployment: {meta_file_id=}")
        mf: meta_file.Meta_File = meta_file_data.get_meta_file_by_id(meta_file_id)

        permission_config.check_user_permission(permissions.PermissionAction.CANCEL_WORKFLOW, mf.workflow.name)
        processing_user_data.create_action_log(action=action_type.Action_type.CANCEL_WF, meta_file=mf)

        mf.cancel_deployment()
    except Exception as e:
        logging.error("An error occured. Please check details!")
        logging.exception(e, stack_info=True)
        return http_functions.get_json_response_error(str(e))

    return http_functions.get_json_response({'status': 'success'})
    


async def reset_stage_status(request: Request, meta_file_id: int, stage_id: int):

    try:
        logging.debug(f"Reset Stage Status: {meta_file_id=}, {stage_id=}")
        mf: meta_file.Meta_File = meta_file_data.get_meta_file_by_id(meta_file_id)

        permission_config.check_user_permission(permissions.PermissionAction.RUN_WORKFLOW, mf.workflow.name, stage=mf.get_stage_by_id(stage_id).name)
        processing_user_data.create_action_log(action=action_type.Action_type.RESET_STAGE_STATUS, meta_file=mf)

        mf.stages.get_stage(stage_id).set_status(stage_status.Status.READY)
        mf.set_status(meta_file.Meta_file_status.READY)

    except Exception as e:
        logging.error("An error occured. Please check details!")
        logging.exception(e, stack_info=True)
        return http_functions.get_json_response_error(str(e))

    return http_functions.get_json_response({'status': 'success'})
    


async def reset_deployment_status(request: Request, meta_file_id: int):

    try:
        logging.debug(f"Reset Deployment Status: {meta_file_id=}")
        
        mf: meta_file.Meta_File = meta_file_data.get_meta_file_by_id(meta_file_id)

        permission_config.check_user_permission(permissions.PermissionAction.RUN_WORKFLOW, mf.workflow.name)
        processing_user_data.create_action_log(action=action_type.Action_type.RESET_DEPLOYMENT_STATUS, meta_file=mf)

        for stage in mf.get_open_stages():
            if stage.status == stage_status.Status.IN_PROCESS:
                stage.set_status(stage_status.Status.READY)

        mf.set_status(meta_file.Meta_file_status.READY)

    except Exception as e:
        logging.error("An error occured. Please check details!")
        logging.exception(e, stack_info=True)
        return http_functions.get_json_response_error(str(e))

    return http_functions.get_json_response({'status': 'success'})
    


async def create_deployment(request: Request, wf_name, commit=None, obj_list=None):
    """
    Creates a new deployment for a given workflow, commit, and the name of the list of objects.
    This function checks if a deployment already exists for the specified commit and workflow.
    If a deployment exists and its status is not 'CANCELED', it returns an error response.
    Otherwise, it creates a new meta file for the deployment, sets its status to 'READY', and returns the deployment metadata.
    Args:
        wf_name (str): The name of the workflow for which the deployment is to be created.
        commit (str): The commit hash or identifier associated with the deployment.
        obj_list (list): Name of a list of objects to be included in the deployment.
                This list should contain strings in the following format:
                        prod_obj|{production_lib}|{development_lib}|{object_name}|{object_type}|{object_attr}|{source_path}
                Example:
                        prod_obj|prouzalib|devlib|date|srvpgm|sqlrpgle|prouzalib/qrpglesrc/date.sqlrpgle.srvpgm

    Returns:
        flask.Response: A JSON response containing the status of the operation and relevant data or error message.
    """
    
    obj_list = dict(request.query_params).get('obj_list', obj_list)

    logging.debug(f"Create Deployment: {wf_name=}, {commit=}, {obj_list=}")
    logging.debug(f'{os.path.realpath(os.path.dirname(__file__)+"/..")=}')
    result={}
    status=200

    try:
        permission_config.check_user_permission(permissions.PermissionAction.START_WORKFLOW, wf_name)

        wf = workflow.Workflow(wf_name)
        logging.debug(f"Workflow: {wf}")
        existing_version = deploy_version.Deploy_Version.get_deployment_by_commit(project=wf.default_project, commit=commit)

        logging.debug(f"{existing_version=}, {meta_file.Meta_file_status.CANCELED=}")

        if existing_version is not None and meta_file.Meta_file_status(existing_version['status']) != meta_file.Meta_file_status.CANCELED:
            return http_functions.get_json_response({'status': 'error', 'error': f"Given commit is already used in deployment version {existing_version['version']} with status '{existing_version['status']}'"}, status=401)

        mf: meta_file.Meta_File = meta_file_data.create_new_meta_file(workflow_name=wf_name, object_list=obj_list)
        #mf = meta_file.Meta_File(workflow_name=wf_name, object_list=obj_list)
        processing_user_data.create_action_log(action=action_type.Action_type.CREATE_WF, details=wf_name, meta_file=mf)

        mf.commit = commit
        mf.set_status(meta_file.Meta_file_status.READY)
        result={'status': 'success', 'meta_file': mf.get_all_data_as_dict()}

    except Exception as e:
        logging.exception(e, stack_info=True)
        return http_functions.get_json_response_error(str(e))

    return http_functions.get_json_response(result, status=status)
   




async def start_workflow(request: Request, wf_name: str):
    """
    Starts a workflow with the given parameters.
    """
    params = dict(request.query_params)
    logging.info(f"Starting workflow with parameters: {params}")
    
    logging.debug(f"Create Deployment: {wf_name=}")
    logging.debug(f'{os.path.realpath(os.path.dirname(__file__)+"/..")=}')
    result={}
    status = 200

    try:
        permission_config.check_user_permission(permissions.PermissionAction.START_WORKFLOW, wf_name)

        wf = workflow.Workflow(wf_name)
        logging.debug(f"Workflow: {wf}")
 
        mf = meta_file_data.create_new_meta_file(workflow_name=wf_name, custom_data=params)
        processing_user_data.create_action_log(action=action_type.Action_type.CREATE_WF, details=wf_name, meta_file=mf)

        mf.set_status(meta_file.Meta_file_status.READY)
        result={'status': 'success', 'meta_file': mf.get_all_data_as_dict()}

    except Exception as e:
        logging.exception(e, stack_info=True)
        return http_functions.get_json_response_error(str(e))

    return http_functions.get_json_response(result, status=status)



async def set_check_error(request: Request, meta_file_id: int, stage_id: int, action_id: int, checked: bool):
    logging.debug(f"Set check error action_id: {action_id}, checked: {checked}")
    result={}
    status = 200
    session = request.state.session

    try:
        mf: meta_file.Meta_File = meta_file_data.get_meta_file_by_id(meta_file_id)
        if mf.status in [meta_file.Meta_file_status.CANCELED, meta_file.Meta_file_status.FINISHED]:
            raise Exception(f"Can't change step check because deployment is already {mf.status.value}.")

        mf.set_action_check(stage_id, action_id, checked, session['current_user'])
        mf.save()
    except Exception as e:
        logging.exception(e, stack_info=True)
        return http_functions.get_json_response_error(str(e))

    #mf.set_status(meta_file.Meta_file_status.READY)
    logging.debug(f"{result=}")

    return http_functions.get_json_response(result, status=status)




async def set_source_ready_4_deployment(request: Request, meta_file_id: int):
    data = await request.json()
    logging.debug(f"Set source ready for deployment lib: {data['lib']}, name: {data['name']}, type: {data['type']}, checked: {data['checked']}, {meta_file_id=}")
    result={}
    status = 200
    
    try:
        mf: meta_file.Meta_File = meta_file_data.get_meta_file_by_id(meta_file_id)

        permission_config.check_user_permission(permissions.PermissionAction.FOUR_EYES_CHECK, mf.workflow.name, stage=mf.get_stage_by_id(data['stage_id']).name)
        
        if mf.status in [meta_file.Meta_file_status.CANCELED, meta_file.Meta_file_status.FINISHED]:
            raise Exception(f"Can't change object status because deployment is already {mf.status.value}.")
        
        processing_user_data.create_action_log(action=action_type.Action_type.CHANGE_OBJ_READY_STATUS, details=f"Set object {data['lib']}/{data['name']}({data['type']}) ready={data['checked']}", meta_file=mf)
        obj: Deploy_Object = mf.deploy_objects.get_deploy_object(data['lib'], data['name'], data['type'])
        obj.ready = data['checked']
        mf.save()
    except Exception as e:
        logging.exception(e, stack_info=True)
        return http_functions.get_json_response_error(str(e))

    #mf.set_status(meta_file.Meta_file_status.READY)
    logging.debug(f"{result=}")

    return http_functions.get_json_response(result, status=status)




async def get_stage_steps_html(request: Request, meta_file_id: int, stage_id: int):
    
    logging.debug(f"Get html for stage steps: {stage_id}, {meta_file_id=}")

    try:
        mf_obj: meta_file.Meta_File = meta_file_data.get_meta_file_by_id(meta_file_id)
        permission_config.check_user_permission(permissions.PermissionAction.READ, mf_obj.workflow.name)

        html = flowchart.generate_stage_steps_html(request, mf_obj, mf_obj.get_stage_by_id(stage_id))
        return http_functions.get_json_response({'html': html}, status=200)
    except Exception as e:
        logging.exception(e, stack_info=True)
        return http_functions.get_json_response_error(str(e))




async def get_workflows(request: Request):

    wfs = workflow.Workflow.get_all_workflows_json()
    return http_functions.get_json_response(wfs)




async def get_projects(request: Request):

    result = {}
    projects = workflow.Workflow.get_all_projects()

    for project in projects:
        result[project] = {}
        dv = deploy_version.Deploy_Version.get_deployments(project)
        for depl in dv['deployments']:
            if depl['status'] not in result[project]:
                result[project][depl['status']] = 0
            result[project][depl['status']] = result[project][depl['status']] + 1

    return http_functions.get_json_response(result)




async def add_permission(request: Request):
    data = await request.json()
    type: str = data['type']
    name: str = data['name']
    roles: List[str] = data['roles']
    general: List[str] = data['general']

    logging.debug(f"Add permission of type {type} with name {name} for roles {roles}, {general=}")
    result = {"status": "success"}
    status = 200

    permission_execution = {
        'user': permission_config.PermissionKonfig.add_user_permission, 
        'role': permission_config.PermissionKonfig.add_role_permission
    }

    try:
        permission_config.check_user_permission(permissions.PermissionAction.ADMIN)

        if type not in permission_execution:
            return http_functions.get_json_response_error(f"Unknown permission type '{type}'", status=400)
        
        permission_execution[type](name=name, roles=roles, general=[permissions.PermissionAction(action) for action in general], workflows={})

    except Exception as e:
        logging.exception(e, stack_info=True)
        return http_functions.get_json_response_error(str(e))

    return http_functions.get_json_response(result, status=status)



async def save_permissions(request: Request):

    try:
        permission_config.check_user_permission(permissions.PermissionAction.ADMIN)

        data = await request.json()

        user_permissions = data.get('user_permissions', {})
        permission_config.PermissionKonfig.convert_permissions('user', user_permissions)
        for user, perm in user_permissions.items():
            permission_config.PermissionKonfig.user_permissions[user].permissions.general = perm.permissions.general
            permission_config.PermissionKonfig.user_permissions[user].roles = perm.roles
        
        role_permissions = data.get('role_permissions', {})
        permission_config.PermissionKonfig.convert_permissions('role', role_permissions)
        for role, perm in role_permissions.items():
            permission_config.PermissionKonfig.role_permissions[role].permissions.general = perm.permissions.general
        
        permission_config.PermissionKonfig.save_permissions()

    except Exception as e:
        logging.exception(e, stack_info=True)
        return http_functions.get_json_response_error(str(e))
    
    result = {"status": "success"}
    status = 200

    return http_functions.get_json_response(result, status=status)