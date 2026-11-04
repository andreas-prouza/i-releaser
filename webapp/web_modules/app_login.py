import os, logging, re, secrets, time
import hashlib, hmac
import datetime

from fastapi import Request

from modules import current_user, files, permission_config
from modules.db import login_failure_data
from modules.db_deployment.connection import quote_odbc_value
from etc import constants, db_config, web_constants
from pathlib import Path


#cnxn = pyodbc.connect('DSN=*LOCAL')
#cursor = cnxn.cursor()


LOGIN_FAILED_TEXT = "Login failed. Check your user and password, and if you have access to i-Releaser."
LOGIN_BLOCKED_TEXT = "Too many failed logins. Please try again later."

_USER_PROFILE = re.compile(r'[A-Za-z$#@][A-Za-z0-9$#@_]{0,9}')

# The last use of a token isn't more exact than this
KEY_LAST_USED_INTERVAL_SECONDS = 60



def is_local_debugging() -> bool:
  """Developers can log in without a password"""
  return os.environ.get("I_RELEASER_LOCAL_DEBUGGING", "False").lower() == "true"



def get_connection_string(user: str, password: str) -> str:

  driver = db_config.DATABASES['IBM_I']['DRIVER']
  host = db_config.DATABASES['IBM_I']['HOST']

  return f"driver={quote_odbc_value(driver)};system={quote_odbc_value(host)};uid={quote_odbc_value(user)};pwd={quote_odbc_value(password)}"



def is_user_allowed_to_login(user: str, password: str) -> bool:
  """Checks everything which can be checked without trying to connect. Each failed connect counts for the IBM i profile."""

  if not _USER_PROFILE.fullmatch(user):
    return False

  if any(ord(char) < 32 for char in password):
    return False

  return user.lower() in [x.lower() for x in permission_config.PermissionKonfig.get_user_list()]



def connect(request: Request, user, password):

  session = request.state.session
  client = request.client.host if request.client else 'unknown'

  if login_failure_data.is_blocked(user.lower(), client):
    logging.warning(f"Login blocked for {user=}, {client=}")
    session['error_text'] = LOGIN_BLOCKED_TEXT
    return False

  try:

    if not is_user_allowed_to_login(user, password):
      raise Exception(f"User has no permission or invalid input")

    logging.debug(f"Try to login; {user=}")

    if not is_local_debugging():
      import pyodbc
      conn = pyodbc.connect(get_connection_string(user, password))
      conn.close()

    user = user.lower()

    # A session id which has been known before must not be valid after the login
    session.regenerate()
    session['is_logged_in'] = True
    session['current_user'] = user
    current_user.set_user(user)
    session.pop('__invalid__', None)
    login_failure_data.clear_failures(user, client)
    logging.debug(f"Login successfully for user {user}")
    return True

  except Exception as e:
    logging.info(f"Login failed for {user=}, {client=}: {type(e).__name__}")
    login_failure_data.add_failure(user.lower(), client)
    session['error_text'] = LOGIN_FAILED_TEXT

  return False


def get_user_keys():

  if not Path(web_constants.C_KEYS_FILE).exists():
    return {}
  
  keys = files.getJson(web_constants.C_KEYS_FILE, retry=True)
  return keys or {}



def get_keys_lock_file() -> str:
  return f"{web_constants.C_KEYS_FILE}.lock"



def hash_key(key: str) -> str:
  return hashlib.sha256(bytes(key, 'utf-8')).hexdigest()



def generate_new_user_key(request: Request):

  session = request.state.session

  key = secrets.token_urlsafe(32)

  with files.lock(get_keys_lock_file()):
    keys=get_user_keys()
    keys[session['current_user']]={'key': hash_key(key), 'orig_key_masked': "*" * (len(key) - 5) + key[-5:], 'date': str(datetime.datetime.now())}
    files.writeJson(keys, web_constants.C_KEYS_FILE)
  
  return key


def mask_key(key):
  return "*" * (len(key) - 6) + key[-6:]



def set_key_last_used(user: str) -> None:

  with files.lock(get_keys_lock_file()):
    keys = get_user_keys()

    if user in keys:
      keys[user]['last_used_time'] = time.time()
      keys[user]['last_used'] = str(datetime.datetime.now()).split('.')[0]
      files.writeJson(keys, web_constants.C_KEYS_FILE)



def is_key_valid(request: Request, auth_token):

  session = request.state.session

  keys=get_user_keys()

  hashed_key=hash_key(auth_token)

  for user,key in keys.items():
    if hmac.compare_digest(key['key'], hashed_key):
      if user not in [x.lower() for x in permission_config.PermissionKonfig.get_user_list()]:
        logging.warning(f"User '{user}' has a token, but no permission")
        return None

      session.transient = True
      session['current_user'] = user

      if time.time() - key.get('last_used_time', 0) > KEY_LAST_USED_INTERVAL_SECONDS:
        set_key_last_used(user)

      return user
  
  logging.warning("Request with an unknown token")

  return None


def drop_user_key(request: Request):

  session = request.state.session

  with files.lock(get_keys_lock_file()):
    keys=get_user_keys()
    keys.pop(session['current_user'], None)
    files.writeJson(keys, web_constants.C_KEYS_FILE)
