import logging
import os, re

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from fastapi.middleware.cors import CORSMiddleware

from etc import global_cfg
from modules import errors, version
from routes import webmiddleware
from web_modules import http_functions




class RedactToken(logging.Filter):
    """API tokens in the URL must not end up in the access log"""

    def filter(self, record: logging.LogRecord) -> bool:

        if isinstance(record.args, tuple):
            record.args = tuple(re.sub(r'auth-token=[^&\s]*', 'auth-token=***', arg) if isinstance(arg, str) else arg for arg in record.args)

        return True




class SkipHealthCheck(logging.Filter):
    """The health check is called every few seconds: not in the access log at level INFO"""

    def filter(self, record: logging.LogRecord) -> bool:
        return not (record.levelno <= logging.INFO and isinstance(record.args, tuple) and any(isinstance(arg, str) and arg.startswith('/healthz') for arg in record.args))



def show_api_docs(request: Request):
    """Swagger UI from the files of the web app (static/assets/swagger-ui), started by a script file:
    the page works with the Content-Security-Policy, without an inline script (docs/features/web-ui-security-headers.md)"""

    return http_functions.get_html_response(request, 'docs.html', openapi_url='/openapi.json')



async def http_error(request: Request, exc: StarletteHTTPException):
    """Unknown path (404), wrong method (405), ...: the error format of the web app, not the one of FastAPI
    (docs/bugfixes/minor-web-defects-2026-11.md, item 9)"""

    error = errors.App_Error(exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase)
    error.status_code = exc.status_code

    response = webmiddleware.ERROR_RESPONSES.get_error_response(request, error)
    for name, value in (exc.headers or {}).items():
        response.headers[name] = value
    return response



async def validation_error(request: Request, exc: RequestValidationError):
    """Invalid parameters or body (422)"""

    details = '; '.join(f"{'.'.join(str(part) for part in e.get('loc', [])[1:]) or 'request'}: {e.get('msg')}" for e in exc.errors())
    return webmiddleware.ERROR_RESPONSES.get_error_response(request, errors.Invalid_Input_Error(f"Invalid input: {details}"))



def setup_fastapi(lifespan=None) -> FastAPI:

    # The default pages of FastAPI load Swagger UI and ReDoc from other servers
    app: FastAPI = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, title='i-Releaser Web API v2', version=version.APP_VERSION,
                           description="Resources under `/api/v2/` (docs/webapi.md). Log in with an API token in the header `Authorization`, as `Bearer` and the token.")
    app.add_exception_handler(StarletteHTTPException, http_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    setup_middleware(app)
    app.add_api_route('/docs', show_api_docs, methods=['GET'], include_in_schema=False)

    logging.getLogger('uvicorn.access').addFilter(RedactToken())
    logging.getLogger('uvicorn.access').addFilter(SkipHealthCheck())

    service_path = os.getenv("I_RELEASER_WEBAPP_PATH", "")
    if len(service_path) > 0:
        service_path += '/'
    app.mount('/static', StaticFiles(directory=f"{service_path}static"), name='static')

    return app



def setup_middleware(app: FastAPI):

    # Middleware to handle access, sessions, ...
    app.add_middleware(webmiddleware.WebMiddleware)
    app.add_middleware(webmiddleware.CacheControlMiddleware)

    # Only if other origins are configured. The web app itself doesn't need it.
    cors_origins = getattr(global_cfg, 'C_CORS_ALLOWED_ORIGINS', [])

    if '*' in cors_origins:
        raise Exception("C_CORS_ALLOWED_ORIGINS can't contain '*'. List the allowed origins.")

    if len(cors_origins) > 0:
        app.add_middleware(CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"]
            )
