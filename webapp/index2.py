#######################################################
# Load modules
#######################################################

# Configuration modules
import sys, json, os, time
base_dir = os.path.realpath(os.path.dirname(__file__)+"/..")
#sys.path.insert(1, base_dir)
#os.chdir(base_dir)
sys.path.append(base_dir)
from pathlib import Path

import logging
import uuid
import contextvars
from etc import logger_config, global_cfg, web_constants

from aiohttp import web
import aiohttp_cors
import asyncio
from aiomcache import Client

import socketio

#######################################################
# Start Flask framework
#######################################################


sio = socketio.AsyncServer(cors_allowed_origins='*')
app = web.Application()
memcached = Client("127.0.0.1", 11211)

#aiohttp_cors.setup(app, defaults={
#    "*": aiohttp_cors.ResourceOptions(
#        allow_credentials=True,
#        expose_headers="*",
#        allow_headers="*",
#    )
#})
sio.attach(app)


async def before_request_handler(request):
    logging.debug(f"Before handling request: {request.method} {request.path}")
    # Perform actions like authentication, logging, or request modification

# Middleware to mimic "before_request"
@web.middleware
async def before_request_middleware(request, handler):
    # Call your "before_request" function here
    await before_request_handler(request)
    # Then call the actual route handler
    response = await handler(request)
    return response


async def handler(request):
    logging.debug('Processing handler')
    return web.Response(text="Hello, world!")


app.middlewares.append(before_request_middleware)

app.router.add_get('/', handler)

#######################################################
# Set routes
#
#   Retrieve request data (POST & GET):
#     request.values.get('parameter')
#######################################################

session_data=contextvars.ContextVar('sessions', default={})

session_lock = asyncio.Lock()

async def get_next_number(sid):
    async with session_lock:
        data = session_data.get()
        data[sid] += 1
        session_data.set(data)
        return data[sid]

async def drop_session(sid):
    async with session_lock:
        data = session_data.get()
        del data[sid]
        session_data.set(data)


@sio.event
async def connect(sid, environ, parm2=None):
    logging.info(f"connect: start {sid}")
    await memcached.set(b"counter", bin(0))

    async with session_lock:
        data = session_data.get()
        data[sid] = 0
        session_data.set(data)
        logging.info(f"Connect {sid=}  {data[sid]=}  {parm2=}")
    logging.debug(f"{session_data.get()=}")
    logging.info(f"connect: end {sid}")


@sio.event
async def notify(sid, req_data):
    logging.info(f"Notify: start {sid}")
    project = {}

    count = await memcached.get(b"counter")
    count += 1
    await memcached.set(b"counter", bin(count))

    next_nr = await get_next_number(sid)
    logging.info(f"1. {next_nr=}")
    #logging.info(f"{sid=}. Data: {data=}")
    project[f'notify-{next_nr}'] = {'ready' : next_nr}
    logging.info(f"Notify: {sid=}. Data: '{project}'")
    await sio.emit("projects", project, to=sid)
    logging.info(f"Notify: end")
    time.sleep(2)


@sio.event
async def disconnect(sid):
    logging.info(f'disconnect {sid=}')
    await drop_session(sid)


#######################################################
# Run service
#######################################################


async def main():
    return app
    # gunicorn index2:main --bind 0.0.0.0:2001 --worker-class aiohttp.GunicornWebWorker


if __name__ == '__main__':
    logging.info("Run WebApp from MAIN")
    #app.run(port=app.config["PORT"],host=app.config['HOST'])
    
    # https://docs.aiohttp.org/en/stable/web_reference.html#aiohttp.web.run_app
    web.run_app(app, host='0.0.0.0', port=2001, print=print)