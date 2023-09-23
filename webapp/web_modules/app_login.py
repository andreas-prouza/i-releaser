from __future__ import annotations
import logging
from flask import session

from modules import meta_file, stages
from modules.cmd_status import Status as Cmd_Status
from etc import db_config

import pyodbc


#cnxn = pyodbc.connect('DSN=*LOCAL')
#cursor = cnxn.cursor()


def connect(user, password):
  driver = db_config.DATABASES['IBM_I']['DRIVER']
  host = db_config.DATABASES['IBM_I']['HOST']
  connection_string = f"driver={driver};system={host};uid={user};pwd={password}"
  logging.debug(f"Try to login; {user=}, {driver=}, {host=}")
  
  try:
    conn = pyodbc.connect(connection_string)
    conn.close()
    session['is_logged_in'] = True
    session.pop('__invalid__', None)
    logging.debug(f"Login successfully for user {user}")
    return True

  except Exception as e:
    logging.debug(f"Login failed for user {user}")
    session['error_text'] = str(e)
    logging.exception(e)

  return False

