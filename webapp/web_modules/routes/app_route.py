import sys, json, os
from pathlib import Path

import logging
from etc import  constants, global_cfg
from aiohttp import web

# Custom modules
from modules import deploy_version, meta_file
from modules import workflow

from web_modules.http_functions import get_html_response
from web_modules import own_session
from web_modules import app_login
from web_modules import flowchart




async def get_sidebar_data(request: web.Request):

    session = own_session.get_session(request)

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

    session = own_session.get_session(request)

    project= session.get('current_project', None) or global_cfg.C_DEFAULT_PROJECT

    dv = deploy_version.Deploy_Version.get_deployments(f'{constants.C_LOCAL_BASE_DIR}/etc/deploy_version_{project}.json')
    #logging.debug(dv)
    dv = dv['deployments']
    logging.debug("Send response")

    #current_user=session['current_user'],
    return get_html_response("overview/list-deployments.html", project=project, sidebar=await get_sidebar_data(request), deploy_version_file=f'{constants.C_LOCAL_BASE_DIR}/etc/deploy_version_{project}.json', deployments=dv)





async def select_project(request: web.Request):

    session = own_session.get_session(request)

    project = request.match_info['project']

    available_projects = workflow.Workflow.get_all_projects()
    if (project not in available_projects):
        logging.error(f"Project '{project}' is not in list of {available_projects}.")
        project = available_projects[0]

    session['current_project'] = project
    own_session.update_session(session)

    return web.HTTPFound('/')




async def show_log(request: web.Request):

    log = request.match_info['log']
    number_of_lines = request.match_info.get('number_of_lines', 100)

    logging.debug(f"Read log file {log=}")

    data = []
    with open(f"log/{log}") as file:
        data = file.readlines()[-number_of_lines:]
        logging.debug("reverse data")
        data = list(reversed(data))

    logging.debug("Send response")
    return get_html_response("admin/log.html", sidebar=await get_sidebar_data(request), logfile=log, content=data, number_of_lines=number_of_lines)





async def login(request: web.Request) -> web.Response:

    logging.debug('Login')
    session = own_session.get_session(request)

    if 'is_logged_in' in session and '__invalid__' not in session:
        return web.HTTPFound('/')

    logging.debug(f"{session.get('error_text', None)=}")

    txt = session.get('error_text', None)
    return get_html_response("login.html", sidebar=None, error_text=txt)




async def show_user(request: web.Request):

    session = own_session.get_session(request)

    user_keys=app_login.get_user_keys()
    user_key = user_keys.get(session['current_user'], None)

    return get_html_response("admin/user.html", sidebar=await get_sidebar_data(request), user_key=user_key)




async def logout(request: web.Request):
    session = own_session.get_session(request)
    session.pop('error_text', None)
    session.pop('is_logged_in', None)
    session.pop('uid', None)
    session['__invalid__'] = True
    own_session.update_session(session)
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
