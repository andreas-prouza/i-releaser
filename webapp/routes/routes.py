import logging, sys, os, json
from typing import List, Optional
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

# Custom modules
from etc import constants, global_cfg

from modules import action_type
from modules import deploy_version, meta_file
from modules import workflow
from modules.deploy_object import Deploy_Object

from web_modules import http_functions
from web_modules import flowchart, app_login
from webapp.web_modules import server_sessions


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

    dv = deploy_version.Deploy_Version.get_deployments(f'{constants.C_LOCAL_BASE_DIR}/etc/deploy_version_{project}.json')
    logging.debug(dv)
    dv = dv['deployments']
    logging.debug("Send response")
    
    #current_user=session['current_user'], 
    return http_functions.get_html_response(request, 'overview/list-deployments.html', sidebar=get_sidebar_data(request), deploy_version_file=f'{constants.C_LOCAL_BASE_DIR}/etc/deploy_version_{project}.json', deployments=dv) 




async def list_deployments(request: Request, project: str):
    dv = deploy_version.Deploy_Version.get_deployments(f'{constants.C_LOCAL_BASE_DIR}/etc/deploy_version_{project}.json')
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
    with open(f"log/{log}") as file:
        data = file.readlines()[-number_of_lines:]
        logging.debug(f"reverse data")
        data = list(reversed(data))

    logging.debug("Send response")
    return http_functions.get_html_response(request, 'admin/log.html', sidebar=get_sidebar_data(request), logfile=log, content=data, number_of_lines=number_of_lines) 



async def login(request: Request):
    session = request.state.session
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

    session = request.state.session
    session.pop('error_text', None)
    session.pop('is_logged_in', None)
    session.pop('uid', None)
    session['__invalid__'] = True
    return RedirectResponse("/login", status_code=302)



async def show_workflows(request: Request):

    logging.debug('Call workflows')

    wf = workflow.Workflow.get_all_workflow_json()
    wf_json = json.dumps(wf, default=str, indent=4)

    logging.debug("Send response")
    return http_functions.get_html_response(request, 'admin/workflows.html', sidebar=get_sidebar_data(request), workflows=wf, workflow_json=wf_json, projects=workflow.Workflow.get_all_projects()) 



async def show_settings(request: Request):

    logging.debug('Call settings')
    keys=app_login.get_user_keys()

    logging.debug("Send response")
    return http_functions.get_html_response(request, 'admin/settings.html', 
        sidebar=get_sidebar_data(request), 
        allowed_users=global_cfg.C_ALLOWED_USERS, 
        default_project=global_cfg.C_DEFAULT_PROJECT, 
        port='????',
        path=Path(os.path.dirname(__file__)),
        keys=keys
        )



async def show_details(request: Request, project: str, version: int):
    logging.debug(f'Show details of {project=}, {version=}')
    logging.debug(request.form)

    error = ''
    mf_dict = None
    mf_json = None

    try:
        dv = deploy_version.Deploy_Version.get_deployment(project, version)
        logging.debug(f"{dv=}")
        mf = meta_file.Meta_File.load_json_file(dv['meta_file'])
        flow = flowchart.get_flowchar_html(mf)
        mf_dict = mf.get_all_data_as_dict()
        mf_json = json.dumps(mf_dict, default=str, indent=4)
        progress = (len(mf.workflow.stages) - len(mf.open_stages)) / len(mf.workflow.stages)
        progress = progress * 100
        logging.debug(dv)
        return http_functions.get_html_response(request, 'overview/show-deployment.html', sidebar=get_sidebar_data(request), progress=progress, deployment_json=mf_json, deployment_dict=mf_dict, error=error, flow_html=flow['html'], flow_javascript=flow['java_script']) 

    except Exception as e:
        logging.exception(e, stack_info=True)
        error = e
        return http_functions.get_html_response(request, 'error.html', sidebar=get_sidebar_data(request), error=error) 



async def run_stage(request: Request):
    data = request.get_json(force=True)
    result={'status': 'success'}
    logging.debug(f"Run stage-id {data['stage_id']} of {data['filename']} with option {data['option']}")
    session = request.state.session

    mf = meta_file.Meta_File.load_json_file(data['filename'])

    try:
        
        mf.set_status(meta_file.Meta_file_status.READY)
        mf.current_user = current_user=session.get('current_user', None).upper()

        continue_run = True
        if data['option'] == 'run_all':
            continue_run = False

        mf.run_current_stage_as_thread(int(data['stage_id']), continue_run=continue_run)

    except Exception as e:
        logging.error("An error occured. Please check details!")
        logging.exception(e, stack_info=True)
        result['status'] = 'error'
        result['error'] = str(e)

    return http_functions.get_json_response(result)



async def get_meta_file_json(request: Request):
    data = request.get_json(force=True)
    logging.debug(f"Get logs from: {data=}")

    if 'filename' not in data.keys():
        return http_functions.get_json_response({'error': "Key 'filename' not in request"}, status=401)

    logging.debug(f"Get logs from: {data['filename']=}")

    meta_file = {}
    with open (data['filename'], "r") as file:
        meta_file_json=json.load(file)

    #mf_json = json.dumps(meta_file_json, default=str, indent=4)

    return http_functions.get_json_response(meta_file_json)
    


async def get_action_log(request: Request):
    data = request.get_json(force=True)
    logging.debug(f"Get logs from: {data=}")
    logging.debug(f"Get logs from: {data['filename']=}, {data['stage_id']=}, {data['action_id']=}, {data['history_element']=}")

    mf = meta_file.Meta_File.load_json_file(data['filename'])

    if data['stage_id'] is None:
        return http_functions.get_json_response({"stdout" : mf.run_history.get_list()[data['history_element']]['log']})

    for action in mf.get_actions(stage_id=int(data['stage_id']), action_id=int(data['action_id']), include_subactions=True):
        logging.debug(f"Action logs: {action}")
        if len(action.run_history) > data['history_element']:
            return http_functions.get_json_response(action.run_history[data['history_element']].get_dict())

    return http_functions.get_json_response({})
    


async def cancel_deployment(request: Request):
    data = request.get_json(force=True)
    logging.debug(f"Cancel Deployment: {data['filename']}")

    mf = meta_file.Meta_File.load_json_file(data['filename'])
    action_type.create_action_log(action=action_type.Action_type.CANCEL_WF, meta_file=mf)
    mf.cancel_deployment()

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
    
    obj_list = request.args.get('obj_list', obj_list)

    logging.debug(f"Create Deployment: {wf_name=}, {commit=}, {obj_list=}")
    logging.debug(f'{os.path.realpath(os.path.dirname(__file__)+"/..")=}')
    result={}

    try:
        wf = workflow.Workflow(wf_name)
        logging.debug(f"Workflow: {wf}")
        existing_version = deploy_version.Deploy_Version.get_deployment_by_commit(project=wf.default_project, commit=commit)

        logging.debug(f"{existing_version=}, {meta_file.Meta_file_status.CANCELED=}")

        if existing_version is not None and meta_file.Meta_file_status(existing_version['status']) != meta_file.Meta_file_status.CANCELED:
            return http_functions.get_json_response({'status': 'error', 'error': f"Given commit is already used in deployment version {existing_version['version']} with status '{existing_version['status']}'"}, status=401)

        mf = meta_file.Meta_File(workflow_name=wf_name, object_list=obj_list)
        action_type.create_action_log(action=action_type.Action_type.CREATE_WF, details=wf_name, meta_file=mf)

        mf.commit = commit
        mf.set_status(meta_file.Meta_file_status.READY)
        result={'status': 'success', 'meta_file': mf.get_all_data_as_dict()}

    except Exception as e:
        logging.exception(e, stack_info=True)
        result={'status': 'error', 'error': str(e)}

    return http_functions.get_json_response(result)
   


async def set_check_error(request: Request):
    data = request.get_json(force=True)
    logging.debug(f"Set check error stage: {data['stage_id']}, action_id: {data['action_id']}, checked: {data['checked']}, filename: {data['filename']}")
    result={}
    session = request.state.session

    try:
        mf = meta_file.Meta_File.load_json_file(data['filename'])
        mf.set_action_check(int(data['stage_id']), int(data['action_id']), data['checked'], session['current_user'])
        mf.write_meta_file()
    except Exception as e:
        logging.exception(e, stack_info=True)
        result={'status': 'error', 'error': str(e)}

    #mf.set_status(meta_file.Meta_file_status.READY)
    logging.debug(f"{result=}")

    return http_functions.get_json_response(result)



async def set_source_ready_4_deployment(request: Request):
    data = request.get_json(force=True)
    logging.debug(f"Set source ready for deployment lib: {data['lib']}, name: {data['name']}, type: {data['type']}, checked: {data['checked']}, filename: {data['filename']}")
    result={}
    
    try:
        mf = meta_file.Meta_File.load_json_file(data['filename'])
        action_type.create_action_log(action=action_type.Action_type.CHANGE_OBJ_READY_STATUS, details=f"Set object {data['lib']}/{data['name']}({data['type']}) ready={data['checked']}", meta_file=mf)
        obj: Deploy_Object = mf.deploy_objects.get_deploy_object(data['lib'], data['name'], data['type'])
        obj.ready = data['checked']
        mf.write_meta_file()
    except Exception as e:
        logging.exception(e, stack_info=True)
        result={'status': 'error', 'error': str(e)}

    #mf.set_status(meta_file.Meta_file_status.READY)
    logging.debug(f"{result=}")

    return http_functions.get_json_response(result)



async def get_stage_steps_html(request: Request):
    
    data = request.get_json(force=True)
    logging.debug(f"Get html for stage steps: {data['stage_id']}, filename: {data['filename']}")

    try:
        mf = meta_file.Meta_File.load_json_file(data['filename'])
        html = flowchart.generate_stage_steps_html(request, mf, mf.get_stage_by_id(int(data['stage_id'])))
        return http_functions.get_json_response({'html': html})
    except Exception as e:
        logging.exception(e, stack_info=True)
        return http_functions.get_json_response({'error': str(e)})



async def get_workflows(request: Request):

    wfs = workflow.Workflow.get_all_workflow_json()
    return http_functions.get_json_response(wfs)



async def get_projects(request: Request):

    result = {}
    projects = workflow.Workflow.get_all_projects()

    for project in projects:
        result[project] = {}
        dv = deploy_version.Deploy_Version.get_deployments(f'{constants.C_LOCAL_BASE_DIR}/etc/deploy_version_{project}.json')
        for depl in dv['deployments']:
            if depl['status'] not in result[project]:
                result[project][depl['status']] = 0
            result[project][depl['status']] = result[project][depl['status']] + 1

    return http_functions.get_json_response(result)
