import logging
import re
import uuid
from http import HTTPStatus
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from web_modules import http_functions
from etc import constants
from modules import current_user, errors
from web_modules import app_login
from web_modules import server_sessions
import routes.routes as routes


# With a session these actions have to be sent as POST: a link (GET) must not be able to trigger them.
# With an API token GET is still possible, but deprecated.
ACTIONS_WITHOUT_GET = re.compile(r'^/api/(run_stage|cancel_deployment|cancel_job|reset_stage_status|reset_last_finished_stage|reset_deployment_status|set_check_error|create_deployment|start_workflow)/')

SAFE_METHODS = ['GET', 'HEAD', 'OPTIONS']

# The login form is read before the user is known. Starlette doesn't limit urlencoded forms (PYSEC-2026-249, fixed in starlette 1.3.1),
# so the size is checked here. User and password are much smaller.
LOGIN_FORM_MAX_BYTES = 4096
LOGIN_FORM_MAX_FIELDS = 10



def get_path(request: Request) -> str:
    """The path the router uses. `request.url.path` is built with the Host header, which the client chooses (e.g. `Host: x/static/`)."""
    return request.scope['path']



# Only script files of the web app; style attributes are set by SweetAlert2 and bootstrap-table (docs/features/web-ui-security-headers.md)
CONTENT_SECURITY_POLICY = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; "
                           "connect-src 'self'; media-src 'none'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")

SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'same-origin',
    'X-Frame-Options': 'DENY',
}



def get_csp_header_name() -> str:
    return 'Content-Security-Policy-Report-Only' if getattr(constants, 'C_CSP_REPORT_ONLY', False) else 'Content-Security-Policy'



class CacheControlMiddleware(BaseHTTPMiddleware):
    """Headers of every response: caching, and the security headers (the Content-Security-Policy for HTML)"""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if 'cache-control' not in response.headers:
            response.headers['Cache-Control'] = 'max-age=0'
        for name, value in SECURITY_HEADERS.items():
            if name.lower() not in response.headers:
                response.headers[name] = value
        if response.headers.get('content-type', '').startswith('text/html'):
            response.headers[get_csp_header_name()] = CONTENT_SECURITY_POLICY
        return response
   

   
class WebMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        logging.debug(f'Now call handler for {get_path(request)}')
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

        error_id = None

        if isinstance(e, errors.App_Error):
            logging.info(f"{request.method} {get_path(request)}: {type(e).__name__}: {e}")
            message = str(e)
            status_code = e.status_code
        else:
            error_id = uuid.uuid4().hex[:8]
            logging.exception(f"Error {error_id} in {request.method} {get_path(request)}: {e}", exc_info=e)
            message = f"An unexpected error occurred. Error id: {error_id}"
            status_code = 500

        if self.wants_html(request):
            response = http_functions.get_html_response(request, 'error.html', sidebar=self.get_sidebar(request), error=message,
                                                        status_code=status_code, status_text=self.get_status_text(status_code), error_id=error_id)
            response.status_code = status_code
            return response

        return http_functions.get_json_response_error(message, status=status_code)



    def get_sidebar(self, request: Request) -> dict | None:
        """The navigation of the error page: only for logged-in users, and the error page must not fail itself"""

        if not hasattr(request.state, 'session') or current_user.get_user() is None:
            return None

        try:
            return routes.get_sidebar_data(request)
        except Exception as e:
            logging.exception(e)
            return None



    def get_status_text(self, status_code: int) -> str:
        try:
            return HTTPStatus(status_code).phrase
        except ValueError:
            return 'Error'



    def wants_html(self, request: Request) -> bool:

        if get_path(request).startswith('/api/'):
            return False

        # Scripts of the pages (static/assets/js/app/api.js), also when they load a part of a page: errors and 401 as JSON
        if request.headers.get('x-requested-with', '').lower() == 'fetch':
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

        if request.method == 'GET' and ACTIONS_WITHOUT_GET.match(get_path(request)):
            return http_functions.get_json_response_error(f"Use POST for {get_path(request)}", status=405)

        if request.method not in SAFE_METHODS and not self.is_same_origin(request):
            return http_functions.get_json_response_error("Request from another origin is not allowed", status=403)

        return None



    def check_login_form_size(self, request: Request) -> JSONResponse | None:
        """The body of a request without login is only read if its size is known and small (the server reads no more than `Content-Length`)"""

        length = request.headers.get('content-length', '')

        if not length.isdigit():
            return http_functions.get_json_response_error('Content-Length is required', status=411)

        if int(length) > LOGIN_FORM_MAX_BYTES:
            return http_functions.get_json_response_error('Request too large', status=413)

        return None



    async def check_session(self, request: Request) -> None | JSONResponse | HTMLResponse | RedirectResponse:

        path = get_path(request)

        if path.startswith('/static/') or path == '/favicon.ico':
            logging.debug("No need to check session. Only media!")
            return
        
        request.state.session = server_sessions.SessionManager(request)
        await request.state.session.load()

        request.state.session.pop('error_text', None)

        if path == '/logout':
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
        if request.method == "POST":
            response = self.check_login_form_size(request)
            if response is not None:
                return response
            form = await request.form(max_fields=LOGIN_FORM_MAX_FIELDS, max_part_size=LOGIN_FORM_MAX_BYTES)
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
