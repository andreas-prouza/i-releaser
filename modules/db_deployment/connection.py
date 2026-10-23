"""
Connection to Db2 for i of the target system (ODBC, IBM i Access ODBC Driver)

A connection is one database server job on IBM i.
Locks (ALCOBJ), QTEMP and the library list belong to this job,
so everything which belongs together has to run over the same connection.

Configuration: etc/db_deployment.json (see etc/examples/db_deployment.json and docs/db-deployment.md)
"""
from __future__ import annotations

import logging
import os

from etc import constants
from modules import files



class Db_Deployment_Exception(Exception):
  pass



C_DEFAULT_DRIVER = 'IBM i Access ODBC Driver'

# Can be changed in "defaults" of etc/db_deployment.json and per table in the custom data of a deployment
DEFAULT_SETTINGS = {
  # Rows per statement of the initial copy
  'batch_size': 50000,
  # Changed rows per statement when the journal changes are applied
  'apply_batch_size': 1000,
  # Journal entries per read
  'journal_batch_size': 50000,
  # Catching up ends as soon as no more than this number of changed rows wait to be applied
  'catch_up_threshold': 1000,
  # Changes may come in faster than they are applied, so catching up ends after this number of cycles anyway
  'catch_up_max_cycles': 100,
  # Seconds to wait for the exclusive lock of the cut-over
  'lock_wait_seconds': 60,
  # Seconds between two progress messages in the log
  'progress_interval_seconds': 60,
  # Compare inserted rows with the source to make sure they got the expected relative record numbers
  'verify_inserts': True,
  # A step ends if more rows than this can't be applied (e.g. a column expression fails for many rows)
  'max_errors': 1000,
}

# Errors of these SQLSTATE classes are caused by the data of a row (data exception, constraint violation).
# Such a row is recorded and the others are processed. Any other error ends the step.
C_ROW_ERROR_CLASSES = ('22', '23')



def load_config() -> dict:
  """Returns the content of etc/db_deployment.json"""

  if not os.path.isfile(constants.C_DB_DEPLOYMENT_CONFIG):
    raise Db_Deployment_Exception(f"DB deployment is not configured: {constants.C_DB_DEPLOYMENT_CONFIG} doesn't exist (see etc/examples/db_deployment.json)")

  return files.getJson(constants.C_DB_DEPLOYMENT_CONFIG, retry=True) or {}



def get_settings(config: dict, table_config: dict|None=None) -> dict:
  """Settings of a table: built-in defaults < "defaults" of the config file < table in custom data"""

  settings = dict(DEFAULT_SETTINGS)
  settings.update(config.get('defaults') or {})

  for key in DEFAULT_SETTINGS:
    if table_config and key in table_config:
      settings[key] = table_config[key]

  return settings



def get_connection_config(config: dict, host: str|None) -> dict:
  """Connection of a stage host. The host name is not case sensitive."""

  host = host or 'localhost'
  connections = config.get('connections') or {}

  for name, connection in connections.items():
    if name.lower() == host.lower():
      return connection

  raise Db_Deployment_Exception(f"No DB connection for host '{host}' in {constants.C_DB_DEPLOYMENT_CONFIG}. Configured hosts: {', '.join(connections.keys())}")



def quote_odbc_value(value) -> str:
  value = str(value)
  if any(c in value for c in ';{}') or value != value.strip():
    return '{' + value.replace('}', '}}') + '}'
  return value



def get_connection_string(config: dict, host: str|None) -> str:

  connection = get_connection_config(config, host)

  password = connection.get('password')
  if connection.get('password_env'):
    password = os.environ.get(connection['password_env'])
    if password is None:
      raise Db_Deployment_Exception(f"Environment variable {connection['password_env']} with the DB password for host '{host}' is not set")

  parts = {
    'DRIVER': connection.get('driver', C_DEFAULT_DRIVER),
    'SYSTEM': connection.get('system', host or 'localhost'),
  }
  if connection.get('user'):
    parts['UID'] = connection['user']
  if password:
    parts['PWD'] = password
  parts.update(connection.get('options') or {})

  return ';'.join(f"{k}={quote_odbc_value(v)}" for k, v in parts.items())



def connect(config: dict, host: str|None) -> Connection:
  """
  Opens a connection to the system of the stage host.
  Autocommit without commitment control (commit mode *NONE): the shadow tables are not journaled.
  """

  import pyodbc

  connection_string = get_connection_string(config, host)
  logging.info(f"Connect to DB of host '{host}': {mask_password(connection_string)}")

  return Connection(pyodbc.connect(connection_string, autocommit=True))



def mask_password(connection_string: str) -> str:
  return ';'.join('PWD=***' if p.upper().startswith('PWD=') else p for p in connection_string.split(';'))



def get_sqlstate(e: Exception) -> str:
  """pyodbc puts the SQLSTATE into the first argument of an error"""
  if len(e.args) > 0 and isinstance(e.args[0], str) and len(e.args[0]) == 5:
    return e.args[0]
  return ''



def is_row_error(e: Exception) -> bool:
  return get_sqlstate(e)[:2] in C_ROW_ERROR_CLASSES



def get_error_text(e: Exception) -> str:
  return str(e.args[-1] if len(e.args) > 0 else e)



def sql_name(name: str) -> str:
  """Delimited SQL identifier, e.g. "ORDERS" """
  return '"' + name.replace('"', '""') + '"'



def sql_table(lib: str, name: str) -> str:
  return f"{sql_name(lib)}.{sql_name(name)}"



def sql_string(value: str) -> str:
  return "'" + value.replace("'", "''") + "'"



def sql_int_list(values) -> str:
  """Literal list of integers for IN (...). The values come from the database or are generated, never from user input."""
  return ', '.join(str(int(v)) for v in values)



class Connection:
  """Thin wrapper of a pyodbc connection"""


  def __init__(self, connection):
    self.connection = connection


  def execute(self, sql: str, params: list|tuple|None=None) -> int:
    """Executes a statement and returns the number of changed rows"""

    logging.debug(f"SQL: {sql} {params or ''}")
    cursor = self.connection.cursor()
    try:
      if params:
        cursor.execute(sql, params)
      else:
        cursor.execute(sql)
      return cursor.rowcount
    finally:
      cursor.close()


  def query(self, sql: str, params: list|tuple|None=None) -> list[dict]:
    """Returns all rows as dicts with lowercase column names"""

    logging.debug(f"SQL: {sql} {params or ''}")
    cursor = self.connection.cursor()
    try:
      if params:
        cursor.execute(sql, params)
      else:
        cursor.execute(sql)
      columns = [c[0].lower() for c in cursor.description]
      return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
      cursor.close()


  def query_value(self, sql: str, params: list|tuple|None=None):
    """Returns the first column of the first row, or None"""

    rows = self.query(sql, params)
    if len(rows) == 0:
      return None
    return next(iter(rows[0].values()))


  def qcmdexc(self, cmd: str, ignore_errors: bool=False) -> bool:
    """
    Runs a CL command in the job of this connection.
    On an error, the last messages of the job log are added to the exception.

    Returns:
        bool: False if it failed and errors are ignored
    """

    logging.info(f"CL: {cmd}")

    try:
      self.execute("CALL QSYS2.QCMDEXC(?)", [cmd])
      return True

    except Exception as e:
      if ignore_errors:
        logging.debug(f"Ignored error of '{cmd}': {get_error_text(e)}")
        return False
      raise Db_Deployment_Exception(f"{cmd} failed: {get_error_text(e)}\n{self.get_joblog()}") from e


  def get_joblog(self, count: int=10) -> str:
    """Last messages of the job log of this connection, for error messages"""

    try:
      rows = self.query("SELECT MESSAGE_ID, MESSAGE_TEXT FROM TABLE(QSYS2.JOBLOG_INFO('*')) X "
                        "ORDER BY ORDINAL_POSITION DESC FETCH FIRST ? ROWS ONLY", [count])
    except Exception as e:
      return f"(Job log not available: {get_error_text(e)})"

    return '\n'.join(f"  {r['message_id'] or ''} {r['message_text'] or ''}" for r in reversed(rows))


  def close(self) -> None:
    try:
      self.connection.close()
    except Exception as e:
      logging.warning(f"Closing the DB connection failed: {get_error_text(e)}")
