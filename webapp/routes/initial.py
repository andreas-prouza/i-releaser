import logging
import os, re

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles

from fastapi.middleware.cors import CORSMiddleware

from etc import global_cfg
from routes import webmiddleware




class RedactToken(logging.Filter):
    """API tokens in the URL must not end up in the access log"""

    def filter(self, record: logging.LogRecord) -> bool:

        if isinstance(record.args, tuple):
            record.args = tuple(re.sub(r'auth-token=[^&\s]*', 'auth-token=***', arg) if isinstance(arg, str) else arg for arg in record.args)

        return True




def show_api_docs():
    """Swagger UI from the files of the web app (static/assets/swagger-ui)"""

    return get_swagger_ui_html(
        openapi_url='/openapi.json',
        title='i-Releaser Web API',
        swagger_js_url='/static/assets/swagger-ui/swagger-ui-bundle.js',
        swagger_css_url='/static/assets/swagger-ui/swagger-ui.css',
        swagger_favicon_url='/static/assets/img/favicon.png',
        oauth2_redirect_url=None,
    )



def setup_fastapi(lifespan=None) -> FastAPI:
    
    # The default pages of FastAPI load Swagger UI and ReDoc from other servers
    app: FastAPI = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
    setup_middleware(app)
    app.add_api_route('/docs', show_api_docs, methods=['GET'], include_in_schema=False)

    logging.getLogger('uvicorn.access').addFilter(RedactToken())

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
