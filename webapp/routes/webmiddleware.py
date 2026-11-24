import logging
import re
import uuid
from http import HTTPStatus
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from web_modules import http_functions
from etc import constants
from modules import current_user, errors, web_settings
from web_modules import app_login
from web_modules import server_sessions
from web_modules import two_factor
import routes.routes as routes


# With a session these actions have to be sent as POST: a link (GET) must not be able to trigger them.
# With an API token GET is still possible, but deprecated.
ACTIONS_WITHOUT_GET = re.compile(r'^/api/(run_stage|cancel_deployment|cancel_job|reset_stage_status|reset_last_finished_stage|reset_deployment_status|set_check_error|create_deployment|start_workflow)/')

SAFE_METHODS = ['GET', 'HEAD', 'OPTIONS']

# The login form is read before the user is known. Starlette doesn't limit urlencoded forms (PYSEC-2026-249, fixed in starlette 1.3.1),
# so the size is checked here. User and password are much smaller.
LOGIN_FORM_MAX_BYTES = 4096
LOGIN_FORM_MAX_FIELDS = 10



def is_background_request(request: Request) -> bool:
    """A request of a page itself (live updates), not of the user: it doesn't extend the session (app/api.js)"""
    return request.headers.get('x-background') == '1' or get_path(request).startswith('/api/watch_state/')



def get_path(request: Request) -> str:
    """The path the router uses. `request.url.path` is built with the Host header, which the client chooses (e.g. `Host: x/static/`)."""
    return request.scope['path']



# Only script files of the web app; style attributes are set by SweetAlert2 and bootstrap-table (docs/features/web-ui-security-headers.md)
CONTENT_SECURITY_POLICY = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; "
                           "connect-src 'self'; media-src 'none'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")

# Paths of the Web API v1 which v2 replaces (docs/features/api-v2.md): answered with `Deprecation: true`, removed in the next major version
V1_DEPRECATED = re.compile(r'^/api/(get_projects|get_workflows|list_deployments|start_workflow|create_deployment|get_meta_file_json|cancel_deployment'
                           r'|edit_custom_data|run_stage|reset_stage_status|reset_last_finished_stage|reset_deployment_status|set_check_error'
                           r'|set_source_ready_4_deployment|set_objects_ready|get_action_log|show_processing_history|cancel_job|approve_stage'
                           r'|generate_user_key|drop_key|revoke_token)(/|$)')

# Reads of the Web API v1 which are sent with POST (the OBI extension reads a deployment with POST get_meta_file_json):
# allowed for a token with the scope `read` (docs/features/api-v2.md#decisions-2026-11-24)
V1_READ_POSTS = re.compile(r'^/api/(get_meta_file_json/\d+|list_deployments/[^/]+)$')

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
            # Pages and data of a logged-in user must not stay in the cache of the browser (back button after the logout,
            # shared computers). The files of the web app may (docs/bugfixes/minor-web-defects-2026-11.md, item 4)
            response.headers['Cache-Control'] = 'max-age=0' if get_path(request).startswith('/static/') else 'no-store'
        for name, value in SECURITY_HEADERS.items():
            if name.lower() not in response.headers:
                response.headers[name] = value
        if V1_DEPRECATED.match(get_path(request)):
            response.headers['Deprecation'] = 'true'
        if response.headers.get('content-type', '').startswith('text/html'):
            response.headers[get_csp_header_name()] = CONTENT_SECURITY_POLICY
        return response



class WebMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        logging.debug(f'Now call handler for {get_path(request)}')
        response = None

        current_user.set_user(None)

        # A setting changed in another worker (docs/features/settings-in-web-app.md): one stat of etc/app.json
        web_settings.refresh()

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
            # Files: not on the event loop (docs/bugfixes/blocking-login-in-middleware.md)
            await run_in_threadpool(request.state.session.save)
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

        if isinstance(e, two_factor.Step_Up_Required_Error):
            # The page asks for the code and sends the request again (app/api.js)
            return JSONResponse({'status': 'error', 'message': message, 'step_up': True}, status_code=status_code)

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

        # Not X-Forwarded-Host: an allowed CORS origin could set it (docs/bugfixes/minor-web-defects-2026-11.md, item 3).
        # The reverse proxy keeps the Host header (ProxyPreserveHost), or the external address is configured.
        if urlparse(source).netloc == request.headers.get('host'):
            return True

        external = urlparse(getattr(constants, 'C_EXTERNAL_URL', '') or '')
        parsed = urlparse(source)
        return bool(external.netloc) and (parsed.scheme, parsed.netloc) == (external.scheme, external.netloc)



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

        if path == '/logout':
            return

        if 'is_logged_in' in request.state.session:
            user = request.state.session.get('current_user', None)
            if user is None:
                logging.warning("Session indicates logged in but no current_user found")
            current_user.set_user(user)
            if not is_background_request(request):
                request.state.session.touch()

            # The policy requires two-factor authentication: until it's set up, the user can only set it up.
            # Checked again on each request: the policy may have been loosened since the login.
            if request.state.session.get(two_factor.SESSION_SETUP_REQUIRED) \
                    and await run_in_threadpool(two_factor.check_setup_required, request.state.session, user) \
                    and path not in two_factor.SETUP_PATHS:
                if self.wants_html(request):
                    return RedirectResponse('/user#two-factor', status_code=303)
                return http_functions.get_json_response_error("Set up two-factor authentication first (page 'My account')", status=403)

            return self.check_session_request(request)

        auth_token = self.get_auth_token(request)

        if auth_token is not None:
            if await run_in_threadpool(app_login.is_key_valid, request, auth_token):
                current_user.set_user(request.state.session.get('current_user', None))
                # A token with the scope `read` only reads (docs/features/api-v2.md#tokens)
                if getattr(request.state, 'token_scope', None) == 'read' and request.method not in SAFE_METHODS \
                        and not (request.method == 'POST' and V1_READ_POSTS.match(path)):
                    return http_functions.get_json_response_error("This API token can only read (scope 'read')", status=403)
                return
            request.state.session.transient = True
            return http_functions.get_json_response_error(getattr(request.state, 'token_error', None) or 'Your authentication-token is not permitted', status=401)

        # The health check answers without login (docs/features/health-check.md)
        if path == '/healthz':
            request.state.session.transient = True
            return

        # Not logged in. Only the login page logs in (docs/bugfixes/minor-web-defects-2026-11.md, item 1): a form sent to another
        # path is not a login, and a login form of another site isn't accepted (login CSRF)
        if request.method == "POST" and path == '/login':

            source = request.headers.get('origin') or request.headers.get('referer')
            if source and not self.is_same_origin(request):
                return http_functions.get_json_response_error("Request from another origin is not allowed", status=403)

            # The browser would drop the session cookie and show the login page again without a message
            # (docs/bugfixes/secure-cookie-over-http-without-message.md). Before the sign-on: it couldn't help.
            if server_sessions.is_cookie_dropped(source):
                logging.warning(f"Login over plain HTTP from {source}: the browser doesn't keep the session cookie with C_COOKIE_SECURE = True. "
                                "Use HTTPS, or set C_COOKIE_SECURE = False in webapp/etc/global_cfg.py (docs/installation.md)")
                request.state.session.transient = True
                request.state.login_error = app_login.COOKIE_NEEDS_HTTPS_TEXT
                return await routes.login(request)

            response = self.check_login_form_size(request)
            if response is not None:
                return response

            form = await request.form(max_fields=LOGIN_FORM_MAX_FIELDS, max_part_size=LOGIN_FORM_MAX_BYTES)
            user, password, code = form.get('user'), form.get('password'), form.get('code')

            if isinstance(user, str) and isinstance(password, str):
                if await app_login.login(request, user, password, code if isinstance(code, str) else None):
                    logging.debug(f"User authenticated: {request.state.session.get('current_user', None)}")
                    return

        logging.debug("User not authenticated, redirect to login")

        if self.wants_html(request):
            return await routes.login(request)

        return http_functions.get_json_response_error('You are not logged in', status=401)



# Error responses outside of the middleware (exception handlers of FastAPI, routes/initial.py)
ERROR_RESPONSES = WebMiddleware(app=None)
