#######################################################
# Load modules
#######################################################

# Configuration modules
import sys, json, os
base_dir = os.path.realpath(os.path.dirname(__file__)+"/..")
sys.path.append(base_dir)
from pathlib import Path

import logging
import uuid
from etc import flask_config, logger_config, constants, global_cfg, web_constants

# Flask module
from flask import Flask, request, session, render_template, jsonify, redirect, url_for
from flask_cors import CORS
from flask_session import Session
#from flask_minify import minify
#from flask_fontawesome import FontAwesome



logging.debug(sys.path)

# Custom modules
from modules import deploy_version, meta_file
from modules import workflow

from web_modules import flowchart, app_login

#######################################################
# Start Flask framework
#######################################################
app = Flask(__name__)
CORS(app)
app.secret_key = 'Session IBM i Deployment Key'
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)
#FontAwesome(app)

#minify(app=app, html=True, js=True, cssless=True)


#######################################################
# Set Flask configuration
#######################################################
app.config.from_object(flask_config.DevelopmentConfig())

logging.debug(app.config)


#######################################################
# Set routes
#
#   Retrieve request data (POST & GET):
#     request.values.get('parameter')
#######################################################


@app.before_request
def check_session():

    logging.debug(request.path)
    logging.debug(session)
    session.pop('error_text', None)

    if '/static' == request.path[:len('/static')] or '/favicon.ico' == request.path:
        logging.debug("No need to check session. Only media!")
        return

    if request.path == '/logout':
        return
        
    if 'uid' not in session:
        session['uid'] = uuid.uuid4()

    if 'is_logged_in' in session and '__invalid__' not in session:
        return
    
    auth_token = request.args.get('auth-token', None)
    logging.debug(auth_token)
    if auth_token is not None:
        logging.debug(f"Check auth-token ({app_login.mask_key(auth_token)})")
        if app_login.is_key_valid(auth_token):
            return
        return jsonify({'Error': 'auth-key is not permitted'})

    logging.debug("Not logged in")
    # Not logged in
    user = None
    password = None
    if 'user' in request.form:
        user = request.form['user']
    if 'password' in request.form:
        password = request.form['password']

    logging.debug(f"{user=}")
    if user is not None and password is not None:
        if app_login.connect(user, password):
            return

    return login()

    #return login()


def get_sidebar_data():
    x ={}

    x['projects'] = workflow.Workflow.get_all_projects()
    x['current_user'] = session.get('current_user', None).upper()
    x['logs'] = os.listdir('log/')
    x['active']=request.args.get('sidebar_active','deployments')
    logging.debug(f"Sidebar: {x}")

    return x


@app.route('/', methods=['GET', 'POST'])
def index():
    
    logging.debug(sys.path)
    logging.debug('Call index.html')
    
    
    project= session.get('current_project', None) or global_cfg.C_DEFAULT_PROJECT

    dv = deploy_version.Deploy_Version.get_deployments(f'{constants.C_LOCAL_BASE_DIR}/etc/deploy_version_{project}.json')
    logging.debug(dv)
    dv = dv['deployments']
    logging.debug("Send response")
    
    #current_user=session['current_user'], 
    return render_template('overview/list-deployments.html', project=project, sidebar=get_sidebar_data(), deploy_version_file=f'{constants.C_LOCAL_BASE_DIR}/etc/deploy_version_{project}.json', deployments=dv) 



@app.route('/api/list_deployments/<project>', methods=['GET', 'POST'])
def list_deployments(project):
    dv = deploy_version.Deploy_Version.get_deployments(f'{constants.C_LOCAL_BASE_DIR}/etc/deploy_version_{project}.json')
    logging.debug(dv)
    dv = dv['deployments']
    return jsonify(dv)



@app.route('/project/<project>', methods=['GET', 'POST'])
def select_project(project):

    available_projects = workflow.Workflow.get_all_projects()
    if (project not in available_projects):
        logging.error(f"Project '{project}' is not in list of {available_projects}.")
        project = available_projects[0]

    session['current_project'] = project

    return redirect('/')



@app.route('/log/<log>', defaults={'number_of_lines':100}, methods=['GET'])
@app.route('/log/<log>/<int:number_of_lines>', methods=['GET', 'POST'])
def show_log(log, number_of_lines):

    logging.debug(f"Read log file {log=}")

    data = []
    with open(f"log/{log}") as file:
        data = file.readlines()[-number_of_lines:]
        logging.debug(f"reverse data")
        data = list(reversed(data))

    logging.debug("Send response")
    return render_template('admin/log.html', sidebar=get_sidebar_data(), logfile=log, content=data, number_of_lines=number_of_lines) 




@app.route('/login', methods=['GET', 'POST'])
def login():
    
    if 'is_logged_in' in session and '__invalid__' not in session:
        return redirect('/')

    logging.debug(f"{session.get('error_text', None)=}")
    return render_template('login.html', sidebar=None, error_text=session.get('error_text', None)) 



@app.route('/user', methods=['GET', 'POST'])
def show_user():

    user_keys=app_login.get_user_keys()
    user_key = user_keys.get(session['current_user'], None)
    if user_key is not None:
        user_key['key'] = app_login.mask_key(user_key['key'])

    return render_template('admin/user.html', sidebar=get_sidebar_data(), user_key=user_key) 




@app.route('/api/set_user_key', methods=['POST'])
def set_user_key():
    logging.debug(f"Set new key for user {session['current_user']}")

    app_login.set_new_user_key()
    return jsonify({"token": app_login.set_new_user_key()})
    


@app.route('/api/drop_key', methods=['POST'])
def drop_user_key():
    logging.debug(f"Drop key for user {session['current_user']}")

    app_login.drop_user_key()
    return jsonify({})
    



@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('error_text', None)
    session.pop('is_logged_in', None)
    session.pop('uid', None)
    session['__invalid__'] = True
    return redirect(url_for("login"))



@app.route('/workflows', methods=['GET', 'POST'])
def show_workflows():

    logging.debug('Call workflows')

    wf = workflow.Workflow.get_all_workflow_json()
    wf_json = json.dumps(wf, default=str, indent=4)

    logging.debug("Send response")
    return render_template('admin/workflows.html', sidebar=get_sidebar_data(), workflow_json=wf_json, projects=workflow.Workflow.get_all_projects()) 


@app.route('/settings', methods=['GET', 'POST'])
def show_settings():

    logging.debug('Call settings')
    keys=app_login.get_user_keys()
    for user, key in keys.items():
        key['key']=app_login.mask_key(key['key'])

    logging.debug("Send response")
    return render_template('admin/settings.html', 
        sidebar=get_sidebar_data(), 
        allowed_users=global_cfg.C_ALLOWED_USERS, 
        default_project=global_cfg.C_DEFAULT_PROJECT, 
        port=app.config["PORT"], 
        path=Path(os.path.dirname(__file__)),
        keys=keys
        )



@app.route('/show_details/<project>/<int:version>', methods=['GET', 'POST'])
def show_details(project, version):
    logging.debug(f'Show details of {project=}, {version=}')
    logging.debug(request.form)

    error = ''
    mf_dict = None
    mf_json = None

    try:
        dv = deploy_version.Deploy_Version.get_deployment(project, version)
        mf = meta_file.Meta_File.load_json_file(dv['meta_file'])
        flow = flowchart.get_flowchart_text(mf)
        mf_dict = mf.get_all_data_as_dict()
        mf_json = json.dumps(mf_dict, default=str, indent=4)
        logging.debug(dv)
        return render_template('overview/show-deployment.html', sidebar=get_sidebar_data(), deployment_json=mf_json, deployment_dict=mf_dict, error=error, flow=flow) 

    except Exception as e:
        logging.exception(e)
        error = e
        return render_template('error.html', sidebar=get_sidebar_data(), error=error) 



@app.route('/run_stage', methods=['POST'])
def run_stage():
    data = request.get_json(force=True)
    error='[]'
    logging.debug(f"Run stage {data['stage']} of {data['filename']}")

    mf = meta_file.Meta_File.load_json_file(data['filename'])

    try:
        mf.set_status(meta_file.Meta_file_status.READY)
        mf.run_current_stage(data['stage'])
    except Exception as e:
        logging.exception(e)
        error=json.dumps(e, default=str, indent=4)

    logging.debug(error)
    return error



@app.route('/api/cancel_deployment', methods=['POST'])
def cancel_deployment():
    data = request.get_json(force=True)
    logging.debug(f"Cancel Deployment: {data['filename']}")

    mf = meta_file.Meta_File.load_json_file(data['filename'])
    mf.cancel_deployment()
    


@app.route('/api/create_deployment/<wf_name>/<commit>', methods=['GET'])
def create_deployment(wf_name, commit):
    logging.debug(f"Create Deployment: {wf_name=}, {commit=}")

    mf = meta_file.Meta_File(workflow_name=wf_name)
    mf.commit = commit
    mf.set_status(meta_file.Meta_file_status.READY)

    return jsonify(mf.get_all_data_as_dict())
    


@app.route('/set_check_error', methods=['POST'])
def set_check_error():
    data = request.get_json(force=True)
    logging.debug(f"Set check error stage: {data['stage']}, sequence: {data['sequence']}, checked: {data['checked']}, filename: {data['filename']}")
    try:
        mf = meta_file.Meta_File.load_json_file(data['filename'])
        mf.actions.set_action_check(data['stage'], data['sequence'], data['checked'])
        mf.write_meta_file()
    except Exception as e:
        logging.exception(e)
    #mf.set_status(meta_file.Meta_file_status.READY)
    logging.debug(data)
    return data





#######################################################
# Run service
#######################################################

if __name__ == '__main__':
    app.run(port=app.config["PORT"],host=app.config['HOST'])