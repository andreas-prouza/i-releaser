"""
Mapping of the columns of the old table to the columns of the new table

* Column with the same name: its value is assigned. Db2 converts it (length, numeric precision, CCSID, ...).
* New column: left out of the insert, so it gets its default value.
* Removed column: dropped.
* Expression in the configuration ("columns"): an SQL expression over the columns of the old table,
  e.g. {"ORDDAT": "DATE(TIMESTAMP_FORMAT(DIGITS(ORDDT8), 'YYYYMMDD'))", "NEWCOL": "'X'"}.
  "*DEFAULT" leaves a column out, so it gets its default value.

Identity columns keep their values (OVERRIDING SYSTEM VALUE). Other generated columns
(e.g. row change timestamps) get new values, unless they have an expression.
"""
from __future__ import annotations

from modules.db_deployment.connection import Db_Deployment_Exception, sql_name


C_DEFAULT = '*DEFAULT'

# HAS_DEFAULT of QSYS2.SYSCOLUMNS: values for "no default" and ordinary defaults. All others are generated columns.
C_NOT_GENERATED = ('N', 'Y', 'D', 'F', 'J')

# Columns which can't be compared with "="
C_NOT_COMPARABLE_TYPES = ('BLOB', 'CLOB', 'DBCLOB', 'XML', 'DATALINK')



def is_identity(column: dict) -> bool:
  return (column.get('is_identity') or '').strip().upper() == 'YES'



def is_generated(column: dict) -> bool:
  return is_identity(column) or (column.get('has_default') or 'N').strip().upper() not in C_NOT_GENERATED



def is_generated_always(column: dict) -> bool:
  """Values of these columns can only be inserted with OVERRIDING SYSTEM VALUE and never be updated"""
  if is_identity(column):
    return (column.get('identity_generation') or '').strip().upper() == 'ALWAYS'
  return is_generated(column)



class Column_Mapping:
  """
  Attributes
  ----------
  columns : list[str]
      Columns of the new table which get a value from the old table, in the order of the new table
  expressions : list[str]
      SQL expression over the old table for each of the columns
  update_columns : list[str]
      Columns which can be set by an UPDATE (not generated always)
  compare_columns : list[str]
      Columns which can be compared to verify an insert
  identity_columns : list[str]
      Identity columns which get their value from the old table. They are restarted at the cut-over.
  overriding : bool
      Insert needs OVERRIDING SYSTEM VALUE
  warnings : list[str]
  """


  def __init__(self, old_columns: list[dict], new_columns: list[dict], expressions: dict|None=None):

    self.columns: list[str] = []
    self.expressions: list[str] = []
    self.update_columns: list[str] = []
    self.compare_columns: list[str] = []
    self.identity_columns: list[str] = []
    self.overriding = False
    self.warnings: list[str] = []

    old_names = {c['column_name'] for c in old_columns}
    configured = {k.upper(): v for k, v in (expressions or {}).items()}
    new_names = {c['column_name'].upper() for c in new_columns}

    unknown = [k for k in configured if k not in new_names]
    if len(unknown) > 0:
      raise Db_Deployment_Exception(f"Expressions for columns which don't exist in the new table: {', '.join(unknown)}")

    missing = []

    for column in new_columns:

      name = column['column_name']
      expression = configured.get(name.upper())

      if expression is not None and str(expression).strip().upper() == C_DEFAULT:
        continue

      if expression is None:

        if is_generated(column) and not is_identity(column):
          self.warnings.append(f"Column {name} is generated, it gets new values")
          continue

        if name not in old_names:
          if (column.get('is_nullable') or 'Y').strip().upper() == 'N' and (column.get('has_default') or 'N').strip().upper() == 'N':
            missing.append(name)
          continue

        expression = sql_name(name)

      self.columns.append(name)
      self.expressions.append(str(expression))

      if is_generated_always(column):
        self.overriding = True
      else:
        self.update_columns.append(name)

      if is_identity(column):
        self.identity_columns.append(name)

      if (column.get('data_type') or '').strip().upper() not in C_NOT_COMPARABLE_TYPES:
        self.compare_columns.append(name)

    if len(missing) > 0:
      raise Db_Deployment_Exception(f"New columns without default need an expression in the configuration: {', '.join(missing)}")

    if len(self.columns) == 0:
      raise Db_Deployment_Exception("No column of the new table gets a value from the old table")

    dropped = sorted(old_names - {c['column_name'] for c in new_columns})
    if len(dropped) > 0:
      self.warnings.append(f"Columns which don't exist in the new table are dropped: {', '.join(dropped)}")


  def get_column_list(self, prefix: str='') -> str:
    return ', '.join(prefix + sql_name(c) for c in self.columns)


  def get_expression_list(self) -> str:
    return ', '.join(self.expressions)
