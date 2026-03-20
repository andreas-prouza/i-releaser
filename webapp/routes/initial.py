import os, json

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starsessions import SessionMiddleware

from fastapi.middleware.cors import CORSMiddleware

from routes import webmiddleware




def setup_fastapi() -> FastAPI:
    
    app: FastAPI = FastAPI()
    setup_session_middleware(app)

    service_path = os.getenv("I_RELEASER_WEBAPP_PATH", "")
    if len(service_path) > 0:
        service_path += '/'
    app.mount('/static', StaticFiles(directory=f"{service_path}static"), name='static')

    return app



def setup_session_middleware(app: FastAPI):

    # 1. Connect to File System
    store = webmiddleware.FileSystemStore(directory="./sessions")

    # Middleware to handle access, sessions, ...
    app.add_middleware(webmiddleware.WebMiddleware)
    app.add_middleware(webmiddleware.CacheControlMiddleware)
    
    # 2. Add the session middleware to the app
    # This MUST be one of the first middleware to be added.
    app.add_middleware(
        SessionMiddleware, 
        store=store,
        cookie_name="session_id", # The browser only sees this ID
        lifetime=3600,         # Session expires in 1 hour
        #cookie_secure=False,   # Set to True in production (HTTPS only)
        cookie_https_only=False   # Prevents JS from accessing the cookie
    )

    app.add_middleware(CORSMiddleware,
        allow_origins=["*"],  # Allows all origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
        )
        
