from __future__ import annotations
import os
import datetime
import logging
from enum import Enum

from etc import logger_config, constants
from modules import meta_file, stages as st



class Run_History_List_list(list):
    def __init__(self):
        super().__init__()

    def __setitem__(self, index, item):
        super().__setitem__(index, self._validate_item(item))

    def insert(self, index, item):
        super().insert(index, self._validate_item(item))

    def append(self, item):
        super().append(self._validate_item(item))

    def extend(self, other):
        if isinstance(other, type(Run_History)):
            super().extend(other)
        else:
            super().extend(self._validate_item(item) for item in other)

    def _validate_item(self, value):
        if type(value) == Run_History:
            return value
        raise TypeError(
            f"Run_History value expected, got {type(value).__name__}"
        )




class Run_History_List:

  def __init__(self):
    self.histories = Run_History_List_list()



  def get_list(self) -> []:

    list = []

    for a in self.histories:
      list.append(a.get_dict())

    return list



  def add_history(self, history: type[Run_History]=None) -> None:
    if type(history) != Run_History:
      raise Exception(f"Parameter type {type(action)} does not match Run_History")

    self.histories.append(history)



  def add_historys_from_list(self, list: []):

    for a in list:
      history = Run_History(dict=a)
      self.add_history(history)



  def get_list(self) -> []:

    list = []

    for h in self.histories:
      list.append(h.get_dict())

    return list






class Run_History:
  """        self.assertEquals(obj, obj2)
  Parameters
  ----------
  timestamp : datetime
  status : str
    * ``new``: Command hast not yet been run
    * ``failed``: Command has failed
    * ``finished``: Command has finished successfully
  stdout : str
  stderr : str
"""



  def __init__(self, status: str=None, stdout: str=None, stderr: str=None, stage: str=None, create_time=None, dict: {}={}):
    self.status = status
    self.stdout = stdout # Run in these stages
    self.stderr = stderr
    self.create_time = create_time
    self.stage = stage

    if self.create_time == None:
        self.create_time = str(datetime.datetime.utcnow())

    if len(list(set(dict.keys()) - set(self.__dict__.keys()))) == 0:
      for k, v in dict.items():
        setattr(self, k, v)




  def get_dict(self) -> {}:
    return {
      'create_time': self.create_time,
      'status': self.status,
      'stage': self.stage,
      'stdout': self.stdout,
      'stderr': self.stderr
      }