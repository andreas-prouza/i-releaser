
import time, logging, os, json

def add_session_event(session, event):
  session['events'].append({'time': time.time(), 'event': event})



def get_session(id) -> {}:

  file_name = f"session/{id}"
  if not os.path.isfile(file_name):
    return {
      "id": id, 
      "created": int(time.time()), 
      "last-update": int(time.time()),
      "events": [{'time': time.time(), 'event': 'create session'}]
      }

  with open(file_name, "r") as file:
    session = json.load(file)
    if 'events' not in session:
      session['events'] = []
    return session
  
  raise Exception(f'Error during session load: {file_name=}, {os.path.isfile(file_name)=}')



def update_session(id, session):

  file_name = f"session/{id}"

  session['last-update'] = int(time.time())
  logging.debug(f"Update {session=}")

  with open(file_name, 'w') as file:
    json.dump(session, file, default=str, indent=4)


  return