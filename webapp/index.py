#######################################################
# Load modules
#######################################################

# Configuration modules
import sys, json
sys.path.insert(0, f"{sys.path[0]}/..")

import logging
import uuid
from etc import flask_config, logger_config

# Flask module
from flask import Flask, request, session, render_template
from flask_cors import CORS
from flask_session import Session
from flask_minify import minify
#from flask_fontawesome import FontAwesome

# Custom modules
from modules import deploy_version, meta_file

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


#######################################################
# Set routes
#
#   Retrieve request data (POST & GET):
#     request.values.get('parameter')
#######################################################

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'uid' not in session:
        session['uid'] = uuid.uuid4()
    logging.debug(sys.path)
    logging.debug('Call index.html')
    dv = deploy_version.Deploy_Version.get_deployments('../etc/deploy_version_default.json')
    dv = dv['deployments']
    logging.debug(dv)
    logging.debug("Send response")
    return render_template('overview/list-deployments.html', deployments=dv) 



@app.route('/show_details/<int:version>', methods=['GET', 'POST'])
def show_details(version):
    logging.debug(f'Show details of {version=}')
    logging.debug(request.form)
    
    if 'uid' not in session:
        session['uid'] = uuid.uuid4()
    dv = deploy_version.Deploy_Version.get_deployment('default', version)
    mf = meta_file.Meta_File.load_json_file(dv['meta_file'])
    mf_dict = mf.get_all_data_as_dict()
    mf_json = json.dumps(mf_dict, default=str, indent=4)
    logging.debug(dv)
    #logging.debug(mf)
    logging.debug("Send response")
    return render_template('overview/show-deployment.html', deployment_json=mf_json, deployment_dict=mf_dict) 



#######################################################
# Run service
#######################################################

if __name__ == '__main__':
    app.run(port=app.config["PORT"])