from __future__ import annotations
import os
import logging

from etc import logger_config, constants
from modules import meta_file



class Deploy_Action_List_list(list):
    def __init__(self):
        super().__init__()

    def __setitem__(self, index, item):
        super().__setitem__(index, self._validate_number(item))

    def insert(self, index, item):
        super().insert(index, self._validate_number(item))

    def append(self, item):
        super().append(self._validate_number(item))

    def extend(self, other):
        if isinstance(other, type(Deploy_Action)):
            super().extend(other)
        else:
            super().extend(self._validate_number(item) for item in other)

    def _validate_number(self, value):
        if type(value) == Deploy_Action:
            return value
        raise TypeError(
            f"Deploy_Action value expected, got {type(value).__name__}"
        )




class Deploy_Action_List:

  def __init__(self):
    self.actions = Deploy_Action_List_list()



  def get_list(self) -> []:

    list = []

    for a in self.actions:
      list.append(a.get_dict())

    return list



  def add_action(self, action: type[Deploy_Action]) -> None:
    if type(action) != Deploy_Action:
      raise Exception(f"Parameter type {type(action)} does not match Deploy_Action")

    if action.sequence is None:
      action.sequence = self.get_next_sequence()

    self.actions.append(action)



  def add_action_cmd(self, cmd: str, type: str, processing_area: str) -> None:
    self.add_action(Deploy_Action(cmd, self.get_next_sequence(), type=type, processing_area=processing_area))



  def add_actions_from_list(self, list: []):

    for a in list:
      action = Deploy_Action(dict=a)
      self.add_action(action)



  def get_actions(self, processing_area: str=None):
    
    list=[]

    for a in self.actions:
      if a.processing_area == processing_area:
        list.append(a)

    return list



  def get_next_sequence(self) -> int:

    if len(self.actions) == 0:
      return 0

    seq = 0
    for a in self.actions:
      if a.sequence > seq:
        seq = a.sequence
    
    return seq + 1





class Processing_Area:

  PRE = 'pre'
  SAVE = 'save'
  TRANSFER = 'transfer'
  TARGET_PREPARE = 'target-prepare'
  BACKUP_OLD_OBJ = 'backup-old-objects'
  PERFORM_DEPLOYMENT = 'perform-deployment'
  POST = 'post'

  PROCESSING_ORDER = [PRE, SAVE, TRANSFER, BACKUP_OLD_OBJ, PERFORM_DEPLOYMENT, POST]

  def get_values() -> []:
    list = []
    for key, value in Processing_Area.__dict__.items():
      if not key.startswith('__') and type(value) == str:
        list.append(value)
    return list

  def is_valid(text : str):
    return text in Processing_Area.get_values()



class Command_Type:

  PASE = 'pase'
  QSYS = 'QSYS'
  
  def get_values() -> []:
    list = []
    for key, value in Command_Type.__dict__.items():
      if not key.startswith('__') and type(value) == str:
        list.append(value)
    return list

  def is_valid(text : str):
    return text in Command_Type.get_values()



class Deploy_Action:
  """
  Parameters
  ----------
  cmd : str
    Command as text
  sequence : int
    Will be generated if not given
  status : str
    * ``new``: Command hast not yet been run
    * ``failed``: Command has failed
    * ``finished``: Command has finished successfully
  processing_area : str
    * ``pre``: will be run before deployment
    * ``post``: will be run after deployment
  """



  def __init__(self, cmd: str=None, sequence: int=None, status: str='new', type: str=Command_Type.QSYS, processing_area: str=Processing_Area.PRE, dict: {}={}):
    self.sequence = sequence
    self.type = type
    self.cmd = cmd
    self.status = status
    self.stdout = None
    self.stderr = None

    self.processing_area = processing_area

    if 'sequence' in dict.keys():
      self.sequence=dict['sequence']
    if 'cmd' in dict.keys():
      self.cmd=dict['cmd']
    if 'status' in dict.keys():
      self.status=dict['status']
    if 'processing_area' in dict.keys():
      self.processing_area=dict['processing_area']
    if 'type' in dict.keys():
      self.type=dict['type']
    if 'stdout' in dict.keys():
      self.stdout=dict['stdout']
    if 'stderr' in dict.keys():
      self.stderr=dict['stderr']

    if not Processing_Area.is_valid(self.processing_area):
      raise Exception(f'Processing area "{self.processing_area}" is not a valid value. Please use one of these: {Processing_Area.get_values()}')

    if not Command_Type.is_valid(self.type):
      raise Exception(f'Command type "{self.type}" is not a valid value. Please use one of these: {Command_Type.get_values()}')



  def get_dict(self) -> {}:
    return {
      'sequence': self.sequence, 
      'cmd': self.cmd,
      'status': self.status,
      'processing_area': self.processing_area,
      'type': self.type,
      'stdout': self.stdout,
      'stderr': self.stderr
      }
