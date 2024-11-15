from __future__ import annotations
import logging, string, random
from flask import session
import hashlib, json
import datetime

from modules import meta_file, stages
from modules.cmd_status import Status as Cmd_Status
from etc import db_config, global_cfg, web_constants

import pyodbc


#cnxn = pyodbc.connect('DSN=*LOCAL')
#cursor = cnxn.cursor()



def connect(user, password):
  driver = db_config.DATABASES['IBM_I']['DRIVER']
  host = db_config.DATABASES['IBM_I']['HOST']
  connection_string = f"driver={driver};system={host};uid={user};pwd={password}"
  logging.debug(f"Try to login; {user=}, {driver=}, {host=}")

  user = user.lower()
  
  try:

    if user not in [x.lower() for x in global_cfg.C_ALLOWED_USERS]:
      e = Exception(f"User '{user}' has no permission.")
      raise e

    conn = pyodbc.connect(connection_string)
    conn.close()
    session['is_logged_in'] = True
    session['current_user'] = user
    session.pop('__invalid__', None)
    logging.debug(f"Login successfully for user {user}")
    return True

  except Exception as e:
    logging.debug(f"Login failed for user {user}")
    session['error_text'] = str(e)
    logging.exception(e, stack_info=True)

  return False


def get_user_keys():
  with open(web_constants.C_KEYS_FILE) as f:
    keys = json.load(f)
    return keys
  return {}



def generate_new_user_key():

  letters = string.ascii_letters
  key = ''.join(random.choice(letters) for i in range(10)) 

  hash_obj = hashlib.sha256(bytes(key, 'utf-8'))
  hash_obj2 = hashlib.sha256(bytes(hash_obj.hexdigest(), 'utf-8'))

  keys=get_user_keys()
  keys[session['current_user']]={'key': hash_obj2.hexdigest(), 'orig_key_masked': "*" * (len(hash_obj.hexdigest()) - 5) + hash_obj.hexdigest()[-5:], 'date': str(datetime.datetime.now())}

  logging.debug(f"{keys=}")

  with open(web_constants.C_KEYS_FILE, 'w') as file:
    json.dump(keys, file, default=str, indent=2)
  
  return hash_obj.hexdigest()


def mask_key(key):
  return "*" * (len(key) - 6) + key[-6:]



def is_key_valid(auth_token):

  keys=get_user_keys()

  hashed_key=hashlib.sha256(bytes(auth_token, 'utf-8')).hexdigest()

  for user,key in keys.items():
    if key['key'] == hashed_key:
      if user not in [x.lower() for x in global_cfg.C_ALLOWED_USERS]:
        e = Exception(f"User '{user}' has no permission.")
        raise e
      session['current_user'] = user
      return user
  
  logging.warning(f"Could not find token '************{hashed_key[-5:]}'")

  return None


def drop_user_key():

  keys=get_user_keys()
  keys.pop(session['current_user'], None)

  logging.debug(f"{keys=}")

  with open(web_constants.C_KEYS_FILE, 'w') as file:
    json.dump(keys, file, default=str, indent=2)