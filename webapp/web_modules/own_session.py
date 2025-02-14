
import time, logging, os, json

from fastapi import Request, Response

import uuid



def add_session_event(session, event):
    session['events'].append({'time': time.time(), 'event': event})
    update_session(session)


def get_session_file_name(id) -> str:
    return f"session/{id}"



def get_session_id(request: Request):
    return request.cookies.get('uid', uuid.uuid4())



def get_session(request: Request):
    id = get_session_id(request)
    session = get_session_by_id(id)
    add_session_event(session, f'Path: {request.url.path}')
    return session



def get_session_by_id(id) -> {}:

    file_name = get_session_file_name(id)
    logging.debug(f"{id=} | {file_name=}")

    if not os.path.isfile(file_name):
        session = {
          "id": id,
          "created": int(time.time()),
          "last-update": int(time.time()),
          "events": [{'time': time.time(), 'event': 'create session'}]
          }
        logging.debug(session)
        return session

    with open(file_name, "r") as file:
        session = json.load(file)
        if 'events' not in session:
            session['events'] = []
        logging.debug(session)
        return session

    logging.error(f'Error during session load: {file_name=}, {os.path.isfile(file_name)=}')
    raise Exception(f'Error during session load: {file_name=}, {os.path.isfile(file_name)=}')



def update_session(session):

    file_name = get_session_file_name(session['id'])

    session['last-update'] = int(time.time())

    with open(file_name, 'w') as file:
        json.dump(session, file, default=str, indent=4)


    return
