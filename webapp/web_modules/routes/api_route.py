import json, os

import logging
from etc import constants

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from modules import deploy_version, meta_file
from modules import workflow

from web_modules.http_functions import get_json_response
from web_modules import app_login
from web_modules import own_session
from web_modules import flowchart

import threading
import multiprocessing


import subprocess

def get_num_children(parent_pid):
    # Run the `ps` command to list child processes
    result = subprocess.run(['ps', '-L', str(parent_pid)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    child_pids = result.stdout.decode().strip().splitlines()
    return len(child_pids) - 3 # -Heading -ParentID -ps from above subprocess


async def heartbeat(request: Request) -> JSONResponse:
    return get_json_response({
        'status': 'ok', 
        'number-of-threads': threading.active_count(),
        'pid': os.getppid(),
        'workers': get_num_children(os.getppid())
        })





async def list_deployments(project: str) -> JSONResponse:
    dv = deploy_version.Deploy_Version.get_deployments(f'{constants.C_LOCAL_BASE_DIR}/etc/deploy_version_{project}.json')
    logging.debug(dv)
    dv = dv['deployments']
    return get_json_response(dv)




async def generate_user_key(request: Request) -> JSONResponse:

    session = own_session.get_session(request)
    logging.debug(f"Set new key for user {session['current_user']}")

    token = app_login.generate_new_user_key(session)
    return get_json_response({"token": token})



async def drop_user_key(request: Request) -> JSONResponse:

    session = own_session.get_session(request)
    logging.debug(f"Drop key for user {session['current_user']}")

    app_login.drop_user_key(session)
    return get_json_response({})





async def run_stage(request: Request) -> JSONResponse:
    session = own_session.get_session(request)
    data = await request.json()

    result={'status': 'success'}
    logging.debug(f"Run stage-id {data['stage_id']} of {data['filename']} with option {data['option']}")

    mf = meta_file.Meta_File.load_json_file(data['filename'])

    try:

        mf.set_status(meta_file.Meta_file_status.READY)
        mf.current_user = session.get('current_user', None).upper()

        continue_run = True
        if data['option'] == 'run_all':
            continue_run = False

        mf.run_current_stage_as_thread(int(data['stage_id']), continue_run=continue_run)

    except Exception as e:
        logging.error("An error occured. Please check details!")
        logging.exception(e, stack_info=True)
        result['status'] = 'error'
        result['error'] = str(e)

    return get_json_response(result)




async def get_meta_file_json(request: Request) -> JSONResponse:
    data = await request.json()
    logging.debug(f"Get logs from: {data=}")

    if 'filename' not in data.keys():
        return get_json_response({'error': "Key 'filename' not in request"}, status=401)

    logging.debug(f"Get logs from: {data['filename']=}")

    with open (data['filename'], "r") as file:
        meta_file_json=json.load(file)

    #mf_json = json.dumps(meta_file_json, default=str, indent=4)

    return get_json_response(meta_file_json)




async def get_action_log(request: Request) -> JSONResponse:
    data = await request.json()
    logging.debug(f"Get logs from: {data=}")
    logging.debug(f"Get logs from: {data['filename']=}, {data['stage_id']=}, {data['action_id']=}, {data['history_element']=}")

    mf = meta_file.Meta_File.load_json_file(data['filename'])

    if data['stage_id'] is None:
        return get_json_response({"stdout" : mf.run_history.get_list()[data['history_element']]['log']})

    for action in mf.get_actions(stage_id=int(data['stage_id']), action_id=int(data['action_id']), include_subactions=True):
        logging.debug(f"Action logs: {action}")
        if len(action.run_history) > data['history_element']:
            return get_json_response(action.run_history[data['history_element']].get_dict())

    return get_json_response({})



async def cancel_deployment(request: Request) -> JSONResponse:
    data = await request.json()
    logging.debug(f"Cancel Deployment: {data['filename']}")

    mf = meta_file.Meta_File.load_json_file(data['filename'])
    mf.cancel_deployment()

    return get_json_response({'status': 'success'})



async def create_deployment(wf_name: str, commit: str = None, obj_list: str = None) -> JSONResponse:

    logging.debug(f"Create Deployment: {wf_name=}, {commit=}, {obj_list=}")
    logging.debug(f'{os.path.realpath(os.path.dirname(__file__)+"/..")=}')
    result={}

    try:
        wf = workflow.Workflow(wf_name)
        logging.debug(f"Workflow: {wf}")
        existing_version = deploy_version.Deploy_Version.get_deployment_by_commit(project=wf.default_project, commit=commit)

        logging.debug(f"{existing_version=}, {meta_file.Meta_file_status.CANCELED=}")

        if existing_version is not None and meta_file.Meta_file_status(existing_version['status']) != meta_file.Meta_file_status.CANCELED:
            return get_json_response({'status': 'error', 'error': f"Given commit is already used in deployment version {existing_version['version']} with status '{existing_version['status']}'"}, status=401)

        mf = meta_file.Meta_File(workflow_name=wf_name, object_list=obj_list)
        mf.commit = commit
        mf.set_status(meta_file.Meta_file_status.READY)
        result={'status': 'success', 'meta_file': mf.get_all_data_as_dict()}

    except Exception as e:
        logging.exception(e, stack_info=True)
        result={'status': 'error', 'error': str(e)}


    return get_json_response(result)



async def set_check_error(request: Request) -> JSONResponse:

    session = own_session.get_session(request)
    data = await request.json()

    logging.debug(f"Set check error stage: {data['stage_id']}, action_id: {data['action_id']}, checked: {data['checked']}, filename: {data['filename']}")
    result={}

    try:
        mf = meta_file.Meta_File.load_json_file(data['filename'])
        mf.set_action_check(int(data['stage_id']), int(data['action_id']), data['checked'], session['current_user'])
        mf.write_meta_file()
    except Exception as e:
        logging.exception(e, stack_info=True)
        result={'status': 'error', 'error': str(e)}

    #mf.set_status(meta_file.Meta_file_status.READY)
    logging.debug(f"{result=}")

    return get_json_response(result)



async def get_stage_steps_html(request: Request) -> JSONResponse:

    data = await request.json()
    logging.debug(f"Get html for stage steps: {data['stage_id']}, filename: {data['filename']}")

    try:
        mf = meta_file.Meta_File.load_json_file(data['filename'])
        html = flowchart.generate_stage_steps_html(request, mf, mf.get_stage_by_id(int(data['stage_id'])))
        return get_json_response({'html': html})
    except Exception as e:
        logging.exception(e, stack_info=True)
        return get_json_response({'error': str(e)})



async def get_workflows(request: Request) -> JSONResponse:

    wfs = workflow.Workflow.get_all_workflow_json()
    return get_json_response(wfs)




async def get_projects(request: Request) -> JSONResponse:

    result = {}
    projects = workflow.Workflow.get_all_projects()

    for project in projects:
        result[project] = {}
        dv = deploy_version.Deploy_Version.get_deployments(f'{constants.C_LOCAL_BASE_DIR}/etc/deploy_version_{project}.json')
        for depl in dv['deployments']:
            if depl['status'] not in result[project]:
                result[project][depl['status']] = 0
            result[project][depl['status']] = result[project][depl['status']] + 1

    return get_json_response(result)
