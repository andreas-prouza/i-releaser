#######################################################
# Load modules
#######################################################

# Configuration modules
import logging
import uuid
from etc import flask_config, logger_config

# Flask module
from flask import Flask, request, session
from flask_cors import CORS
from flask_session import Session
from flask_minify import minify
#from flask_fontawesome import FontAwesome

# Custom modules


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

    logging.debug('Call index.html')
    logging.debug(request.form)
    logging.debug("Send response")
    return "Hello"



#######################################################
# Run service
#######################################################

if __name__ == '__main__':
    app.run(port=app.config["PORT"])