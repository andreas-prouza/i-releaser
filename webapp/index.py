#######################################################
# Load modules
#######################################################

# Configuration modules
import sys, json, os
base_dir = os.path.realpath(os.path.dirname(__file__)+"/..")
sys.path.append(base_dir)


import logging
import uuid
from etc import flask_config, logger_config, constants

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

project = 'test'

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


@app.route('/', methods=['GET', 'POST'])
def index():
    
    logging.debug(sys.path)
    logging.debug('Call index.html')
    dv = deploy_version.Deploy_Version.get_deployments(f'{constants.C_LOCAL_BASE_DIR}/etc/deploy_version_{project}.json')
    logging.debug(dv)
    dv = dv['deployments']
    logging.debug("Send response")
    return render_template('overview/list-deployments.html', project=project, projects=workflow.Workflow.get_all_projects(), deploy_version_file=f'{constants.C_LOCAL_BASE_DIR}/etc/deploy_version_{project}.json', deployments=dv) 


@app.route('/login', methods=['GET', 'POST'])
def login():
    
    if 'is_logged_in' in session and '__invalid__' not in session:
        return redirect('/')

    logging.debug(f"{session.get('error_text', None)=}")
    return render_template('login.html', error_text=session.get('error_text', None)) 


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
    return render_template('overview/workflows.html', workflow_json=wf_json, projects=workflow.Workflow.get_all_projects()) 



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
        return render_template('overview/show-deployment.html', deployment_json=mf_json, deployment_dict=mf_dict, error=error, flow=flow) 

    except Exception as e:
        logging.exception(e)
        error = e
        return render_template('error.html', error=error) 



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



@app.route('/cancel_deployment', methods=['POST'])
def cancel_deployment():
    data = request.get_json(force=True)
    logging.debug(f"Cancel Deployment: {data['filename']}")

    mf = meta_file.Meta_File.load_json_file(data['filename'])
    mf.cancel_deployment()
    


@app.route('/create_deployment/<wf_name>/<commit>', methods=['GET'])
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