import logging
import os, re

from fastapi import FastAPI
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




def setup_fastapi(lifespan=None) -> FastAPI:
    
    app: FastAPI = FastAPI(lifespan=lifespan)
    setup_middleware(app)

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
