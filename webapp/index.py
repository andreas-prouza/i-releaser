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
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

import socketio
import uvicorn

# Custom modules
from modules import workflow
from web_modules import app_login
from web_modules.routes import api_route, app_route, socket_route, api_middleware
from web_modules.http_functions import get_json_response



logger_config.initial_logger()

#######################################################
# Start Flask framework
#######################################################

app = FastAPI()

sio = socketio.AsyncServer(logger=True, async_mode="asgi", cors_allowed_origins='*')



#@app.after_request
async def add_header(response):
    if 'Cache-Control' not in response.headers:
        response.cache_control.max_age = 0
    return response



# Middleware to mimic "before_request"
#@web.middleware
async def before_request_middleware(request: Request, handler):

    if request.url.path[0:8] == '/static/' or request.url.path == '/favicon.ico':
        logging.debug(f'No need to check for {request.url.path}')
        response = await handler(request)
        response.set_cookie('uid', own_session.get_session_id(request))
        return response

    response: Response = await check_session(request)

    if response is None:
        logging.debug(f'Now call handler for {request.url.path}')
        response = await handler(request)

    response.set_cookie('uid', own_session.get_session_id(request))

    return response





#######################################################
# Run service
#######################################################

def main():

    #app.middlewares.append(before_request_middleware)

    socket_app = socketio.ASGIApp(sio, other_asgi_app=app)

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

    app.add_middleware(api_middleware.ApiMiddleware)

    # Register web routes
#    app.add_api_route("/heartbeat", heartbeat.heartbeat, methodss=['GET'])

    app.add_api_route('/heartbeat', api_route.heartbeat, methods=['GET'])
    app.add_api_route('/', app_route.index, methods=['GET'])
    app.add_api_route('/', app_route.index, methods=['POST'])
    app.add_api_route('/api/list_deployments/{project}', api_route.list_deployments, methods=['GET'])
    app.add_api_route('/api/list_deployments/{project}', api_route.list_deployments, methods=['POST'])
    app.add_api_route('/project/{project}', app_route.select_project, methods=['GET'])
    app.add_api_route('/project/{project}', app_route.select_project, methods=['POST'])
    app.add_api_route('/log/{log}', app_route.show_log, methods=['POST'])
    app.add_api_route('/log/{log}', app_route.show_log, methods=['GET'])
    app.add_api_route('/log/{log}/{number_of_lines}', app_route.show_log, methods=['GET'])
    app.add_api_route('/log/{log}/{number_of_lines}', app_route.show_log, methods=['POST'])
    app.add_api_route('/login', app_route.login, methods=['GET'])
    app.add_api_route('/login', app_route.login, methods=['POST'])
    app.add_api_route('/user', app_route.show_user, methods=['GET'])
    app.add_api_route('/user', app_route.show_user, methods=['POST'])
    app.add_api_route('/api/generate_user_key', api_route.generate_user_key, methods=['POST'])
    app.add_api_route('/api/drop_key', api_route.drop_user_key, methods=['POST'])
    app.add_api_route('/logout', app_route.logout, methods=['GET'])
    app.add_api_route('/logout', app_route.logout, methods=['POST'])
    app.add_api_route('/workflows', app_route.show_workflows, methods=['GET'])
    app.add_api_route('/workflows', app_route.show_workflows, methods=['POST'])
    app.add_api_route('/settings', app_route.show_settings, methods=['GET'])
    app.add_api_route('/settings', app_route.show_settings, methods=['POST'])
    app.add_api_route('/show_details/{project}/{version}', app_route.show_details, methods=['GET'])
    app.add_api_route('/show_details/{project}/{version}', app_route.show_details, methods=['POST'])
    app.add_api_route('/api/run_stage', api_route.run_stage, methods=['POST'])
    app.add_api_route('/api/get_meta_file_json', api_route.get_meta_file_json, methods=['POST'])
    app.add_api_route('/api/get_action_log', api_route.get_action_log, methods=['POST'])
    app.add_api_route('/api/cancel_deployment', api_route.cancel_deployment, methods=['POST'])
    app.add_api_route('/api/create_deployment/{wf_name}/{commit}/{obj_list}', api_route.create_deployment, methods=['GET'])
    app.add_api_route('/api/create_deployment/{wf_name}/{commit}', api_route.create_deployment, methods=['GET'])
    app.add_api_route('/api/create_deployment/{wf_name}', api_route.create_deployment, methods=['GET'])
    app.add_api_route('/api/set_check_error', api_route.set_check_error, methods=['POST'])
    app.add_api_route('/api/get_stage_steps_html', api_route.get_stage_steps_html, methods=['POST'])
    app.add_api_route('/api/get_workflows', api_route.get_workflows, methods=['GET'])
    app.add_api_route('/api/get_projects', api_route.get_projects, methods=['GET'])
   
    app.mount('/static',  StaticFiles(directory="static"), name='static')


    # Register socket events
    socket_handlers = socket_route.SocketHandlers(sio)
    sio.on('connect', socket_handlers.connect)
    sio.on('disconnect', socket_handlers.disconnect)
    sio.on('watch_project_summary', socket_handlers.watch_project_summary)

    return socket_app



#if __name__ == '__main__':
logging.info("Run WebApp from MAIN")
#app.run(port=app.config["PORT"],host=app.config['HOST'])
socket_app = main()
#uvicorn.run(socket_app)
