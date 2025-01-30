#######################################################
# Load modules
#######################################################

# Configuration modules
import sys, json, os, time
base_dir = os.path.realpath(os.path.dirname(__file__)+"/..")
#sys.path.insert(1, base_dir)
#os.chdir(base_dir)
sys.path.append(base_dir)
from pathlib import Path

import logging
import uuid
import contextvars
import hashlib

from etc import flask_config, logger_config, constants, global_cfg, web_constants
from web_modules import own_session

from aiohttp import web

#from aiohttp_session import setup, get_session, session_middleware, Session
#from aiohttp_session.cookie_storage import AbstractStorage

import socketio

#logging.debug(f"{sys.path=}")

# Custom modules
from modules import deploy_version, meta_file
from modules import workflow

from web_modules.http_functions import get_html_response, get_json_response
from web_modules import flowchart, app_login

#######################################################
# Start Flask framework
#######################################################

app = web.Application()

sio = socketio.AsyncServer(logger=True, cors_allowed_origins='*')



def get_session(request: web.Request):
    id = get_session_id(request)
    session = own_session.get_session(id)
    own_session.add_session_event(session, f'Path: {request.path}')
    return session


def update_session(session):
    return own_session.update_session(session)


#@app.after_request
async def add_header(response):
    if 'Cache-Control' not in response.headers:
        response.cache_control.max_age = 0
    return response



# Middleware to mimic "before_request"
@web.middleware
async def before_request_middleware(request: web.Request, handler):
    
    if request.path[0:8] == '/static/' or request.path == '/favicon.ico':
        logging.debug(f'No need to check for {request.path}')
        response = await handler(request)
        response.set_cookie('uid', get_session_id(request))
        return response

    response: web.Response = await check_session(request)
    
    if response is None:
        logging.debug(f'Now call handler for {request.path}')
        response = await handler(request)
    
    response.set_cookie('uid', get_session_id(request))

    return response



def get_session_id(request: web.Request):
    return request.cookies.get('uid', uuid.uuid4())



async def check_session(request: web.Request):

    logging.debug(f'First check session {request.path}')
    session = get_session(request)
    logging.debug(session)

    session['error_text'] = None

    if '/static' == request.path[:len('/static')] or '/favicon.ico' == request.path:
        #logging.debug("No need to check session. Only media!")
        return None

    if request.path == '/logout':
        return None
        
    if 'is_logged_in' in session and '__invalid__' not in session:
        return None
    
    auth_token = request.query.get('auth-token', None)
    #logging.debug(auth_token)
    if auth_token is not None:
        logging.debug(f"Check auth-token ({app_login.mask_key(auth_token)})")
        if app_login.is_key_valid(session, auth_token):
            update_session(session)
            return None
        return get_json_response({'Error': 'Your authentication-token is not permitted'}, status=401)

    #logging.debug("Not logged in")
    # Not logged in
    user = None
    password = None
    form_data = await request.post()
    if 'user' in form_data:
        user = form_data['user']
    if 'password' in form_data:
        password = form_data['password']

    logging.debug(f"{user=}")
    if user is not None and password is not None:
        if app_login.connect(session, user, password):
            logging.debug(f"After login: {session}")
            update_session(session)
            logging.debug(f"Read session again: {get_session(request)}")
            return None

    update_session(session)
    return await login(request)

    #return login()



async def get_sidebar_data(request: web.Request):

    session = get_session(request)

    x ={}

    x['projects'] = workflow.Workflow.get_all_projects()
    x['current_user'] = session.get('current_user', None).upper()
    x['logs'] = os.listdir('log/')
    x['active']=request.query.get('sidebar_active','deployments')
    logging.debug(f"Sidebar: {x}")

    return x



async def index(request: web.Request):
    
    logging.debug(sys.path)
    logging.debug('Call index.html')
    
    session = get_session(request)
    
    project= session.get('current_project', None) or global_cfg.C_DEFAULT_PROJECT

    dv = deploy_version.Deploy_Version.get_deployments(f'{constants.C_LOCAL_BASE_DIR}/etc/deploy_version_{project}.json')
    #logging.debug(dv)
    dv = dv['deployments']
    logging.debug("Send response")
    
    #current_user=session['current_user'], 
    return get_html_response("overview/list-deployments.html", project=project, sidebar=await get_sidebar_data(request), deploy_version_file=f'{constants.C_LOCAL_BASE_DIR}/etc/deploy_version_{project}.json', deployments=dv)



async def list_deployments(request: web.Request):
    project = request.match_info['project']
    dv = deploy_version.Deploy_Version.get_deployments(f'{constants.C_LOCAL_BASE_DIR}/etc/deploy_version_{project}.json')
    logging.debug(dv)
    dv = dv['deployments']
    return get_json_response(dv)



async def select_project(request: web.Request):
    
    session = get_session(request)
    
    project = request.match_info['project']

    available_projects = workflow.Workflow.get_all_projects()
    if (project not in available_projects):
        logging.error(f"Project '{project}' is not in list of {available_projects}.")
        project = available_projects[0]

    session['current_project'] = project
    update_session(session)

    return web.HTTPFound('/')



async def show_log(request: web.Request):

    log = request.match_info['log']
    number_of_lines = request.match_info.get('number_of_lines', 100)

    logging.debug(f"Read log file {log=}")

    data = []
    with open(f"log/{log}") as file:
        data = file.readlines()[-number_of_lines:]
        logging.debug(f"reverse data")
        data = list(reversed(data))

    logging.debug("Send response")
    return get_html_response("admin/log.html", sidebar=await get_sidebar_data(request), logfile=log, content=data, number_of_lines=number_of_lines)




async def login(request: web.Request) -> web.Response:
    
    logging.debug('Login')
    session = get_session(request)

    if 'is_logged_in' in session and '__invalid__' not in session:
        return web.HTTPFound('/')

    logging.debug(f"{session.get('error_text', None)=}")
    
    txt = session.get('error_text', None)
    return get_html_response("login.html", sidebar=None, error_text=txt)




async def show_user(request: web.Request):

    session = get_session(request)

    user_keys=app_login.get_user_keys()
    user_key = user_keys.get(session['current_user'], None)

    return get_html_response("admin/user.html", sidebar=await get_sidebar_data(request), user_key=user_key)




async def generate_user_key(request: web.Request):

    session = get_session(request)
    logging.debug(f"Set new key for user {session['current_user']}")

    token = app_login.generate_new_user_key(session)
    return get_json_response({"token": token})
    


async def drop_user_key(request: web.Request):

    session = get_session(request)
    logging.debug(f"Drop key for user {session['current_user']}")

    app_login.drop_user_key(session)
    return get_json_response({})
    



async def logout(request: web.Request):
    session = get_session(request)
    session.pop('error_text', None)
    session.pop('is_logged_in', None)
    session.pop('uid', None)
    session['__invalid__'] = True
    return web.HTTPFound("/login")



async def show_workflows(request: web.Request):

    logging.debug('Call workflows')

    wf = workflow.Workflow.get_all_workflow_json()
    wf_json = json.dumps(wf, default=str, indent=4)

    logging.debug("Send response")
    return get_html_response("admin/workflows.html", sidebar=await get_sidebar_data(request), workflows=wf, workflow_json=wf_json, projects=workflow.Workflow.get_all_projects())



async def show_settings(request: web.Request):

    logging.debug('Call settings')
    keys=app_login.get_user_keys()

    logging.debug("Send response")
    return get_html_response("admin/settings.html",
        sidebar=await get_sidebar_data(request), 
        allowed_users=global_cfg.C_ALLOWED_USERS, 
        default_project=global_cfg.C_DEFAULT_PROJECT, 
        path=Path(os.path.dirname(__file__)),
        port=None, 
        keys=keys
        )



async def show_details(request: web.Request):

    project = request.match_info['project']
    version = request.match_info['version']

    logging.debug(f'Show details of {project=}, {version=}')

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
        return get_html_response("overview/show-deployment.html", sidebar=await get_sidebar_data(request), progress=progress, deployment_json=mf_json, deployment_dict=mf_dict, error=error, flow_html=flow['html'], flow_javascript=flow['java_script'])

    except Exception as e:
        logging.exception(e, stack_info=True)
        error = e
        return get_html_response('error.html', sidebar=await get_sidebar_data(request), error=error)



async def run_stage(request: web.Request):
    session = get_session(request)
    data = await request.json()

    result={'status': 'success'}
    logging.debug(f"Run stage-id {data['stage_id']} of {data['filename']} with option {data['option']}")

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

    return get_json_response(result)




async def get_meta_file_json(request: web.Request):
    data = await request.json()
    logging.debug(f"Get logs from: {data=}")

    if 'filename' not in data.keys():
        return get_json_response({'error': "Key 'filename' not in request"}, status=401) 

    logging.debug(f"Get logs from: {data['filename']=}")

    meta_file = {}
    with open (data['filename'], "r") as file:
        meta_file_json=json.load(file)

    #mf_json = json.dumps(meta_file_json, default=str, indent=4)

    return get_json_response(meta_file_json)
    



async def get_action_log(request: web.Request):
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
    


async def cancel_deployment(request: web.Request):
    data = await request.json()
    logging.debug(f"Cancel Deployment: {data['filename']}")

    mf = meta_file.Meta_File.load_json_file(data['filename'])
    mf.cancel_deployment()

    return get_json_response({'status': 'success'})
    


async def create_deployment(request: web.Request):
    
    wf_name = request.match_info['wf_name']
    commit = request.match_info.get('commit', None)
    obj_list = request.match_info.get('obj_list', None)

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
    


async def set_check_error(request: web.Request):
    
    session = get_session(request)
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



async def get_stage_steps_html(request: web.Request):
    
    data = await request.json()
    logging.debug(f"Get html for stage steps: {data['stage_id']}, filename: {data['filename']}")

    try:
        mf = meta_file.Meta_File.load_json_file(data['filename'])
        html = flowchart.generate_stage_steps_html(mf, mf.get_stage_by_id(int(data['stage_id'])))
        return get_json_response({'html': html})
    except Exception as e:
        logging.exception(e, stack_info=True)
        return get_json_response({'error': str(e)})



async def get_workflows(request: web.Request):

    wfs = workflow.Workflow.get_all_workflow_json()
    return get_json_response(wfs)




async def get_projects(request: web.Request):

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



@sio.event
async def connect(sid, environ, parm2=None):
    """event listener when client connects to the server"""
    logging.info(f"client has connected {sid=} {environ=}")




#######################################################
# Run service
#######################################################

async def main():

    app.middlewares.append(before_request_middleware)

    sio.attach(app)

    #letters = string.ascii_letters
    #key = ''.join(random.choice(letters) for i in range(10)) 
    #hash_obj = hashlib.sha256(bytes(key, 'utf-8'))

    #setup(app, EncryptedCookieStorage(hash_obj.hexdigest()))
    #setup(app, storage=)

    #######################################################
    # Set routes
    #
    #   Retrieve request data (POST & GET):
    #     request.values.get('parameter')
    #######################################################

    app.add_routes([
        web.get('/', index),
        web.post('/', index),
        web.get('/api/list_deployments/{project}', list_deployments),
        web.post('/api/list_deployments/{project}', list_deployments),
        web.get('/project/{project}', select_project),
        web.post('/project/{project}', select_project),
        web.post('/log/{log}', show_log),
        web.get('/log/{log}', show_log),
        web.get(r'/log/{log}/{number_of_lines:[0-9]{1:10}}', show_log),
        web.post(r'/log/{log}/{number_of_lines:[0-9]{1:10}}', show_log),
        web.get('/login', login),
        web.post('/login', login),
        web.get('/user', show_user),
        web.post('/user', show_user),
        web.post('/api/generate_user_key', generate_user_key),
        web.post('/api/drop_key', drop_user_key),
        web.get('/logout', logout),
        web.post('/logout', logout),
        web.get('/workflows', show_workflows),
        web.post('/workflows', show_workflows),
        web.get('/settings', show_settings),
        web.post('/settings', show_settings),
        web.get(r'/show_details/{project}/{version:[0-9]+}', show_details),
        web.post(r'/show_details/{project}/{version:[0-9]+}', show_details),
        web.post('/api/run_stage', run_stage),
        web.post('/api/get_meta_file_json', get_meta_file_json),
        web.post('/api/get_action_log', get_action_log),
        web.post('/api/cancel_deployment', cancel_deployment),
        web.get('/api/create_deployment/{wf_name}/{commit}/{obj_list}', create_deployment),
        web.get('/api/create_deployment/{wf_name}/{commit}', create_deployment),
        web.get('/api/create_deployment/{wf_name}', create_deployment),
        web.post('/api/set_check_error', set_check_error),
        web.post('/api/get_stage_steps_html', get_stage_steps_html),
        web.get('/api/get_workflows', get_workflows),
        web.get('/api/get_projects', get_projects),
        ])
    app.router.add_static('/static', path=os.path.join(os.path.dirname(__file__), 'static'),)

    return app



if __name__ == '__main__':
    logging.info("Run WebApp from MAIN")
    #app.run(port=app.config["PORT"],host=app.config['HOST'])
    main()