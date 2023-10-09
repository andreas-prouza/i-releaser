from __future__ import annotations
import os
import logging
from enum import Enum

from etc import constants
from modules import meta_file, stages, run_history as rh, workflow
from modules.cmd_status import Status as Cmd_Status
#import traceback



class Deploy_Action_List_list(list):


  def __init__(self, iterable=None):

    iterable2 = []

    if iterable is not None:
      for i, a in enumerate(iterable):
        iterable2.append(a)
        if type(a) == dict:
          iterable2[i] = Deploy_Action.get_action_from_dict(a)

    if len(iterable2) > 0:
      super().__init__(iterable2)
      return
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



  def get_list(self) -> []:

    list = []

    for a in self:
      list.append(a.get_dict())

    return list




  def add_action(self, action: type[Deploy_Action]) -> int:

    #logging.error(traceback.format_stack())

    if type(action) != Deploy_Action:
      raise Exception(f"Parameter type {type(action)} does not match Deploy_Action")

    if action.sequence is None:
      action.sequence = self.get_next_sequence()

    logging.info(f"Add action: {action.stage=}, {action.processing_step=}, {action.cmd=}, {action.sequence=}, {action.status=}")

    self.append(action)

    logging.debug(f"Number of actions: {len(self)}")

    return action.sequence



  def add_action_cmd(self, cmd: str, environment: Command_Type, processing_step: str, stage: str=None, check_error: bool=True) -> int:
    logging.debug(f'Add action for cmd: {cmd=}, {environment=}, {processing_step=}')
    return self.add_action(Deploy_Action(cmd, self.get_next_sequence(), environment=environment, processing_step=processing_step, 
    stage=stage, check_error=check_error))



  def add_actions_from_list(self, dict: {}):

    logging.debug('Add actions from list')
    for k, cmds in dict.items():
      for cmd in cmds:
        action = Deploy_Action(dict=cmd)
        self.add_action(action)



  def get_actions(self, processing_step: str=None, stage: str=None) -> []:

    list=[]

    for a in self:
      # Consider processing_step if given
      if processing_step is None or a.processing_step == processing_step:
        # Consider stage if given
        if stage is not None and a.stage is not None and stage != a.stage:
          continue
        list.append(a)

    list.sort(key=lambda x: x.sequence)

    return list



  def get_actions_as_dict(self, processing_step: str=None, stage: str=None) -> []:

    dict=[]

    for a in self.get_actions(processing_step, stage):
      dict.append(a.get_dict())

    return dict



  def set_action_check(self, stage: str, sequence: int, check: bool) -> None:

    for a in self:
      if a.stage == stage and a.sequence == sequence:
        a.check_error = check



  def get_next_sequence(self) -> int:

    if len(self) == 0:
      return 0

    seq = 0
    for a in self:
      if a.sequence > seq:
        seq = a.sequence
    
    return seq + 1






class Command_Type(Enum):

  PASE = 'PASE'
  QSYS = 'QSYS'
  SCRIPT = 'SCRIPT'
  




class Deploy_Action:
  """        self.assertEquals(obj, obj2)
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
  processing_step : str
    * ``pre``: will be run before deployment
    * ``post``: will be run after deployment
  check_error : bool
    When run the command, it must be checked for errors
  """



  def __init__(self, cmd: str=None, sequence: int=None, status: Cmd_Status=Cmd_Status.NEW,  
    environment: Command_Type=Command_Type.QSYS, stage: str=None, processing_step: str=None, 
    check_error: bool=True, dict: {}=None):

    self.sequence = sequence
    self.environment = environment
    self.cmd = cmd
    self.stage = stage
    self.status = status
    self.run_history = rh.Run_History_List_list()
    self.check_error = check_error

    self.processing_step = processing_step

    if self.environment is not None and type(self.environment) != Command_Type:
      raise Exception(f"Environment has type {type(self.environment)} instead of Command_Type")

    if stage is not None and type(stage) != str:
      raise Exception("Stage is not a string!")

    if dict is not None and len(list(set(dict.keys()) - set(self.__dict__.keys()))) > 0 and len(dict) > 0:
      raise Exception(f"Attributes of {type(self)} ({self.__dict__}) does not match attributes from {dict=}")

    if dict is not None and len(list(set(dict.keys()) - set(self.__dict__.keys()))) == 0:
      
      for k, v in dict.items():

        setattr(self, k, v)

      self.validate()




  def validate(self):

    if self.stage is None:
      raise Exception('No Stage defined')
    
    if self.processing_step is None:
      raise Exception('No processing step defined')
    
    self.environment = Command_Type(self.environment)
    self.status = Cmd_Status(self.status)

    if self.cmd is None:
      raise Exception('Command is not allowed to be None')

    if type(self.run_history) != rh.Run_History_List_list:
      run_history_list = self.run_history
      self.run_history = rh.Run_History_List_list()
      self.run_history.add_historys_from_list(run_history_list)




  def get_action_from_dict(dict: {}={}):

    action = Deploy_Action()

    for k, v in dict.items():
      setattr(action, k, v)

    action.validate()

    return action




  def get_dict(self) -> {}:
    return {
      'sequence': self.sequence, 
      'cmd': self.cmd,
      'status': self.status.value,
     # 'stage': self.stage.name,
      'stage': self.stage,
      'processing_step': self.processing_step,
      'environment': self.environment.value,
      'run_history': self.run_history.get_list(),
      'check_error': self.check_error
      }



  def __eq__(self, o):
    if (self.sequence, self.environment, self.cmd, self.stage, self.status, self.run_history, self.check_error, self.processing_step) == (o.sequence, o.environment, o.cmd, o.stage, o.status, o.run_history, o.check_error, o.processing_step):
      return True
    return False