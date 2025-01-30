
import time, logging, os, json

def add_session_event(session, event):
  session['events'].append({'time': time.time(), 'event': event})
  update_session(session)


def get_session_file_name(id) -> str:
  return f"session/{id}"


def get_session(id) -> {}:

  file_name = get_session_file_name(id)
  if not os.path.isfile(file_name):
    session = {
      "id": id, 
      "created": int(time.time()), 
      "last-update": int(time.time()),
      "events": [{'time': time.time(), 'event': 'create session'}]
      }
    return session

  with open(file_name, "r") as file:
    session = json.load(file)
    if 'events' not in session:
      session['events'] = []
    return session
  
  logging.error(f'Error during session load: {file_name=}, {os.path.isfile(file_name)=}')
  raise Exception(f'Error during session load: {file_name=}, {os.path.isfile(file_name)=}')



def update_session(session):

  file_name = get_session_file_name(session['id'])

  session['last-update'] = int(time.time())

  with open(file_name, 'w') as file:
    json.dump(session, file, default=str, indent=4)


  return