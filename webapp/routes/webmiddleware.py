import logging
import re
import uuid
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from web_modules import http_functions
from modules import current_user, errors
from web_modules import app_login
from web_modules import server_sessions
import routes.routes as routes


# With a session these actions have to be sent as POST: a link (GET) must not be able to trigger them.
# With an API token GET is still possible, but deprecated.
ACTIONS_WITHOUT_GET = re.compile(r'^/api/(run_stage|cancel_deployment|cancel_job|reset_stage_status|reset_last_finished_stage|reset_deployment_status|set_check_error|create_deployment|start_workflow)/')

SAFE_METHODS = ['GET', 'HEAD', 'OPTIONS']



class CacheControlMiddleware(BaseHTTPMiddleware):
    
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if 'cache-control' not in response.headers:
            response.headers['Cache-Control'] = 'max-age=0'
        return response
   

   
class WebMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        logging.debug(f'Now call handler for {request.url.path}')
        response = None

        current_user.set_user(None)
        
        try:

            # We can now safely access request.session
            if response is None:
                response = await self.check_session(request)
                logging.debug(f"Session check result: {response}")
            
            if response is None:
                response = await call_next(request)

        except Exception as e:
            response = self.get_error_response(request, e)

        if hasattr(request.state, 'session'):
            request.state.session.save()
            request.state.session.set_cookie(response)

        logging.debug(f"Response send code: {response.status_code}")
        
        return response



    def get_error_response(self, request: Request, e: Exception) -> JSONResponse | HTMLResponse:
        """Errors for the caller are shown. For all others the caller only gets an id to find the details in the log."""

        if isinstance(e, errors.App_Error):
            logging.info(f"{request.method} {request.url.path}: {type(e).__name__}: {e}")
            message = str(e)
            status_code = e.status_code
        else:
            error_id = uuid.uuid4().hex[:8]
            logging.exception(f"Error {error_id} in {request.method} {request.url.path}: {e}", exc_info=e)
            message = f"An unexpected error occurred. Error id: {error_id}"
            status_code = 500

        if self.wants_html(request):
            sidebar = routes.get_sidebar_data(request) if hasattr(request.state, 'session') else None
            response = http_functions.get_html_response(request, 'error.html', sidebar=sidebar, error=message)
            response.status_code = status_code
            return response

        return http_functions.get_json_response_error(message, status=status_code)



    def wants_html(self, request: Request) -> bool:

        if request.url.path.startswith('/api/'):
            return False

        accept: str = request.headers.get("accept") or ""
        return '*/*' in accept or 'text/html' in accept



    def get_auth_token(self, request: Request) -> str|None:

        authorization = request.headers.get('authorization', '')

        if authorization.lower().startswith('bearer '):
            return authorization[len('bearer '):].strip()

        # Deprecated: the token ends up in the access logs
        return request.query_params.get('auth-token', None)



    def is_same_origin(self, request: Request) -> bool:
        """The browser tells where a request comes from, and scripts of other sites can't change that"""

        source = request.headers.get('origin') or request.headers.get('referer')

        if not source or source == 'null':
            return False

        hosts = [request.headers.get('host'), request.headers.get('x-forwarded-host')]
        return urlparse(source).netloc in hosts



    def check_session_request(self, request: Request) -> JSONResponse | None:
        """Requests with a session cookie can be triggered by other web sites (CSRF)"""

        if request.method == 'GET' and ACTIONS_WITHOUT_GET.match(request.url.path):
            return http_functions.get_json_response_error(f"Use POST for {request.url.path}", status=405)

        if request.method not in SAFE_METHODS and not self.is_same_origin(request):
            return http_functions.get_json_response_error("Request from another origin is not allowed", status=403)

        return None



    async def check_session(self, request: Request) -> None | JSONResponse | HTMLResponse | RedirectResponse:

        logging.debug(request.url.path)

        if '/static' == request.url.path[:len('/static')] or '/favicon.ico' == request.url.path:
            logging.debug("No need to check session. Only media!")
            return
        
        request.state.session = server_sessions.SessionManager(request)
        await request.state.session.load()

        request.state.session.pop('error_text', None)

        if request.url.path == '/logout':
            return

        if 'is_logged_in' in request.state.session and '__invalid__' not in request.state.session:
            user = request.state.session.get('current_user', None)
            if user is None:
                logging.warning("Session indicates logged in but no current_user found")
            current_user.set_user(user)
            return self.check_session_request(request)

        auth_token = self.get_auth_token(request)

        if auth_token is not None:
            if app_login.is_key_valid(request, auth_token):
                current_user.set_user(request.state.session.get('current_user', None))
                return
            request.state.session.transient = True
            return http_functions.get_json_response_error('Your authentication-token is not permitted', status=401)

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
                logging.debug(f"User authenticated: {request.state.session.get('current_user', None)}")
                return

        logging.debug("User not authenticated, redirect to login")

        if self.wants_html(request):
            return await routes.login(request)
        
        return http_functions.get_json_response_error('You are not logged in', status=401)
