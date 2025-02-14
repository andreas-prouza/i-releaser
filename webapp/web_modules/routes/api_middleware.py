import logging, time

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response

from etc import web_constants
from web_modules import own_session
from web_modules import app_login
from web_modules.routes import app_route

class ApiMiddleware(BaseHTTPMiddleware):



    async def check_session(self, request: Request):
  
        logging.debug(f'First check session {request.url.path}')
        session = own_session.get_session(request)
        logging.debug(session)
  
        session['error_text'] = None
  
        #No need to check session. Only media! --> OK
        if '/static' == request.url.path[:len('/static')] or '/favicon.ico' == request.url.path:
            return None
  
        # Logout always possible --> OK
        if request.url.path == '/logout':
            return None
  
        # Valid user and session is not timed out--> OK
        if 'is_logged_in' in session and \
          '__invalid__' not in session and \
          session['last-update'] > (time.time() - web_constants.C_SESSION_TIMEOUT):
            return None
  
        # If a token was given --> check it
        auth_token = request.query_params.get('auth-token', None)
        logging.debug(f"{request.query_params=}")
        
        if auth_token is not None:
            logging.debug(f"Check auth-token ({app_login.mask_key(auth_token)})")
            if app_login.is_key_valid(session, auth_token):
                own_session.update_session(session)
                return None
            return get_json_response({'Error': 'Your authentication-token is not permitted'}, status=401)
  
        # Not logged in
        user = None
        password = None
        form_data = await request.form()
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



    async def dispatch(self, request: Request, handler):

      if request.url.path[0:8] == '/static/' or request.url.path == '/favicon.ico':
          logging.debug(f'No need to check for {request.url.path}')
          response = await handler(request)
          response.set_cookie('uid', own_session.get_session_id(request))
          return response

      response: Response = await self.check_session(request)

      if response is None:
          logging.debug(f'Now call handler for {request.url.path}')
          response = await handler(request)

      response.set_cookie('uid', own_session.get_session_id(request))

      return response