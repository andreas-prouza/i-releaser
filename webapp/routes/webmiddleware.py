import logging
import sys
import os
import json

import aiofiles

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starsessions import SessionStore

from web_modules import http_functions
from modules import meta_file
from web_modules import app_login
from web_modules import http_functions
from web_modules import server_sessions
from routes import routes


class FileSystemStore(SessionStore):
    def __init__(self, directory: str):
        self.directory = directory
        os.makedirs(self.directory, exist_ok=True)

    def _get_path(self, session_id: str):
        return os.path.join(self.directory, f"sess_{session_id}.json")

    async def read(self, session_id: str) -> dict:
        path = self._get_path(session_id)
        if not os.path.exists(path): return {}
        async with aiofiles.open(path, mode='r') as f:
            return json.loads(await f.read())

    async def write(self, session_id: str, data: dict, expiry: int = None) -> str:
        async with aiofiles.open(self._get_path(session_id), mode='w') as f:
            await f.write(json.dumps(data))
        return session_id

    async def remove(self, session_id: str):
        path = self._get_path(session_id)
        if os.path.exists(path): os.remove(path)
    



class CacheControlMiddleware(BaseHTTPMiddleware):
    
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if 'cache-control' not in response.headers:
            response.headers['Cache-Control'] = 'max-age=0'
        return response
   

   
class WebMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        logging.debug(f'Now call handler for {request.url.path}')
        
        try:

            # We can now safely access request.session
            response = await self.check_session(request)
            logging.debug(f"Session check result: {response}")
            
            if response is None:
                response = await call_next(request)

        except Exception as e:
            logging.exception(f"Error in middleware: {e}", exc_info=True)
            response = http_functions.get_json_response({ "error": str(e) })
            response.status_code = 500

        if hasattr(request.state, 'session'):
            request.state.session.save()
            request.state.session.set_cookie(response)

        logging.debug(f"Response send code: {response.status_code}")
        
        return response



    async def check_session(self, request: Request) -> None | JSONResponse | HTMLResponse:

        logging.debug(f"{sys.path=}")
        logging.debug(request.url.path)
        #logging.debug(session)

        if '/static' == request.url.path[:len('/static')] or '/favicon.ico' == request.url.path:
            logging.debug("No need to check session. Only media!")
            return

        if request.url.path == '/logout':
            return
        
        request.state.session = server_sessions.SessionManager(request)
        await request.state.session.load()

        request.state.session.pop('error_text', None)

        if 'is_logged_in' in request.state.session and '__invalid__' not in request.state.session:
            current_user = request.state.session.get('current_user', None)
            if current_user is not None:
                meta_file.Meta_File.CURRENT_USER = current_user.upper()
            else:
                meta_file.Meta_File.CURRENT_USER = None
            return
        
        auth_token = request.query_params.get('auth-token', None)

        if auth_token is not None:
            
            if app_login.is_key_valid(request, auth_token):
                return
            return http_functions.get_json_response({'Error': 'Your authentication-token is not permitted'}, status=401)

        #logging.debug("Not logged in")
        # Not logged in
        user = None
        password = None
        form = None
        if request.method == "POST":
            form = await request.form()
            if 'user' in form:
                user = form['user']
            if 'password' in form:
                password = form['password']

        #logging.debug(f"{user=}")
        if user is not None and password is not None:
            if app_login.connect(request, user, password):
                return
            
        logging.debug(f"User not authenticated, redirect to login: {request.state.session.__dict__=}")

        return await routes.login(request)
