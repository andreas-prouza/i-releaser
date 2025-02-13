#######################################################
# Load modules
#######################################################

# Configuration modules
import sys, os, time
base_dir = os.path.realpath(os.path.dirname(__file__)+"/..")
sys.path.append(base_dir)

import logging

from etc import logger_config, web_constants
from web_modules import own_session

#from aiohttp import web
from fastapi import FastAPI
import socketio

# Custom modules
from modules import workflow
from web_modules import app_login
from web_modules.routes import api_route, app_route, socket_route
from web_modules.http_functions import get_json_response


logger_config.initial_logger()

#######################################################
# Start Flask framework
#######################################################

app = FastAPI()

sio = socketio.AsyncServer(logger=True, cors_allowed_origins='*')



#@app.after_request
async def add_header(response):
    if 'Cache-Control' not in response.headers:
        response.cache_control.max_age = 0
    return response



# Middleware to mimic "before_request"
#@web.middleware
async def before_request_middleware(request: web.Request, handler):

    if request.path[0:8] == '/static/' or request.path == '/favicon.ico':
        logging.debug(f'No need to check for {request.path}')
        response = await handler(request)
        response.set_cookie('uid', own_session.get_session_id(request))
        return response

    response: web.Response = await check_session(request)

    if response is None:
        logging.debug(f'Now call handler for {request.path}')
        response = await handler(request)

    response.set_cookie('uid', own_session.get_session_id(request))

    return response




async def check_session(request: web.Request):

    logging.debug(f'First check session {request.path}')
    session = own_session.get_session(request)
    logging.debug(session)

    session['error_text'] = None

    #No need to check session. Only media! --> OK
    if '/static' == request.path[:len('/static')] or '/favicon.ico' == request.path:
        return None

    # Logout always possible --> OK
    if request.path == '/logout':
        return None

    # Valid user and session is not timed out--> OK
    if 'is_logged_in' in session and \
       '__invalid__' not in session and \
       session['last-update'] > (time.time() - web_constants.C_SESSION_TIMEOUT):
        return None

    # If a token was given --> check it
    auth_token = request.query.get('auth-token', None)
    logging.debug(f"{request.query=}")
    
    if auth_token is not None:
        logging.debug(f"Check auth-token ({app_login.mask_key(auth_token)})")
        if app_login.is_key_valid(session, auth_token):
            own_session.update_session(session)
            return None
        return get_json_response({'Error': 'Your authentication-token is not permitted'}, status=401)

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
            own_session.update_session(session)
            logging.debug(f"Read session again: {own_session.get_session(request)}")
            return None

    own_session.update_session(session)
    return await app_route.login(request)

    #return login()




#######################################################
# Run service
#######################################################

async def main():

    #app.middlewares.append(before_request_middleware)

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
    #   request.values.get('parameter')
    #######################################################

    # Register web routes
#    app.add_api_route("/heartbeat", heartbeat.heartbeat, methods=['GET'])

    app.add_api_route('/', app_route.index, method=['GET'])
    app.add_api_route('/', app_route.index, method=['POST'])
    app.add_api_route('/api/list_deployments/{project}', api_route.list_deployments, method=['GET'])
    app.add_api_route('/api/list_deployments/{project}', api_route.list_deployments, method=['POST'])
    app.add_api_route('/project/{project}', app_route.select_project, method=['GET'])
    app.add_api_route('/project/{project}', app_route.select_project, method=['POST'])
    app.add_api_route('/log/{log}', app_route.show_log, method=['POST'])
    app.add_api_route('/log/{log}', app_route.show_log, method=['GET'])
    #app.add_api_route(r'/log/{log}/{number_of_lines:[0-9]{1:10}}', app_route.show_log, method=['GET'])
    #app.add_api_route(r'/log/{log}/{number_of_lines:[0-9]{1:10}}', app_route.show_log, method=['POST'])
    app.add_api_route('/login', app_route.login, method=['GET'])
    app.add_api_route('/login', app_route.login, method=['POST'])
    app.add_api_route('/user', app_route.show_user, method=['GET'])
    app.add_api_route('/user', app_route.show_user, method=['POST'])
    app.add_api_route('/api/generate_user_key', api_route.generate_user_key, method=['POST'])
    app.add_api_route('/api/drop_key', api_route.drop_user_key, method=['POST'])
    app.add_api_route('/logout', app_route.logout, method=['GET'])
    app.add_api_route('/logout', app_route.logout, method=['POST'])
    app.add_api_route('/workflows', app_route.show_workflows, method=['GET'])
    app.add_api_route('/workflows', app_route.show_workflows, method=['POST'])
    app.add_api_route('/settings', app_route.show_settings, method=['GET'])
    app.add_api_route('/settings', app_route.show_settings, method=['POST'])
    #app.add_api_route(r'/show_details/{project}/{version:[0-9]+}', app_route.show_details, method=['GET'])
    #app.add_api_route(r'/show_details/{project}/{version:[0-9]+}', app_route.show_details, method=['POST'])
    app.add_api_route('/api/run_stage', api_route.run_stage, method=['POST'])
    app.add_api_route('/api/get_meta_file_json', api_route.get_meta_file_json, method=['POST'])
    app.add_api_route('/api/get_action_log', api_route.get_action_log, method=['POST'])
    app.add_api_route('/api/cancel_deployment', api_route.cancel_deployment, method=['POST'])
    app.add_api_route('/api/create_deployment/{wf_name}/{commit}/{obj_list}', api_route.create_deployment, method=['GET'])
    app.add_api_route('/api/create_deployment/{wf_name}/{commit}', api_route.create_deployment, method=['GET'])
    app.add_api_route('/api/create_deployment/{wf_name}', api_route.create_deployment, method=['GET'])
    app.add_api_route('/api/set_check_error', api_route.set_check_error, method=['POST'])
    app.add_api_route('/api/get_stage_steps_html', api_route.get_stage_steps_html, method=['POST'])
    app.add_api_route('/api/get_workflows', api_route.get_workflows, method=['GET'])
    app.add_api_route('/api/get_projects', api_route.get_projects, method=['GET'])
   
    #app.router.add_static('/static', path=os.path.join(os.path.dirname(__file__), 'static'),)


    # Register socket events
    socket_handlers = socket_route.SocketHandlers(sio)
    sio.on('connect', socket_handlers.connect)
    sio.on('disconnect', socket_handlers.disconnect)
    sio.on('watch_project_summary', socket_handlers.watch_project_summary)

    return app



if __name__ == '__main__':
    logging.info("Run WebApp from MAIN")
    #app.run(port=app.config["PORT"],host=app.config['HOST'])
    main()
