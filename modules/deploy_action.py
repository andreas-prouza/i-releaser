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



  def get_list(self) -> list[dict]:

    list = []

    for a in self:
      list.append(a.get_dict())

    return list




  def add_action(self, action: Deploy_Action, add_after: Deploy_Action=None) -> Deploy_Action:

    #logging.error(traceback.format_stack())

    if type(action) != Deploy_Action:
      raise Exception(f"Parameter type {type(action)} does not match Deploy_Action")

    action.sequence = self.get_next_sequence()
    
    if add_after is not None:
      action.sequence = add_after.sequence + 1
      for a in self:
        if a.sequence >= action.sequence:
          a.sequence += 1

    #logging.info(f"Add action: {action.stage=}, {action.processing_step=}, {action.cmd=}, {action.sequence=}, {action.status=}")

    self.append(action)

    logging.debug(f"Number of actions: {len(self)}")

    return action



  def add_action_cmd(self, cmd: str, environment: Command_Type, processing_step: str, stage: str=None, check_error: bool=True, add_after: Deploy_Action=None, run_in_new_job: bool=False, execute_remote: bool=None) -> Deploy_Action:
    logging.debug(f'Add action for cmd: {cmd=}, {environment=}, {processing_step=}')

    return self.add_action(Deploy_Action(cmd, self.get_next_sequence(), environment=environment, processing_step=processing_step, 
    stage=stage, check_error=check_error, run_in_new_job=run_in_new_job, execute_remote=execute_remote), add_after=add_after)



  def add_actions_from_dict(self, dict_input: dict) -> None:

    logging.debug(f'Add actions from {type(dict_input)}')
    action = Deploy_Action(dict=dict_input)
    self.add_action(action)



  def get_action_by_id(self, id: int) -> Deploy_Action:
    for a in self:
      if a.id == id:
        return a

    raise Exception(f"Action id {id} not found in list {self.get_actions_as_dict()}")



  def get_actions_by_processing_step(self, processing_step: str) -> Deploy_Action_List_list:

    result = Deploy_Action_List_list()
    for a in self:
      if a.processing_step == processing_step:
        result.append(a)

    return result



  def get_actions(self, processing_step: str=None, stage: str=None, action_id: int=None, include_subactions: bool=False) -> list[Deploy_Action]:

    list_actions=[]

    for a in self:
      
      # Consider processing_step if given
      if processing_step is not None and a.processing_step != processing_step:
        continue
      
      # Consider stage if given
      if stage is not None and a.stage is not None and stage != a.stage:
        continue

      if include_subactions is not None and include_subactions:
        for asa in a.sub_actions:
          if action_id is not None and asa.id == action_id:
            list_actions.append(asa)
            return list_actions
      
      if action_id is not None and a.id == action_id:
        list_actions.append(a)
        return list_actions

      if action_id is not None:
        continue

      list_actions.append(a)

    list_actions.sort(key=lambda x: x.sequence)

    return list_actions



  def get_actions_as_dict(self, processing_step: str=None, stage: str=None) -> list[dict]:

    actions_dict=[]

    for a in self.get_actions(processing_step, stage):
      actions_dict.append(a.get_dict())

    return actions_dict



  def set_action_check(self, action_id: int, check: bool) -> None:

    action = self.get_action_by_id(action_id)

    if action.status == Cmd_Status.FINISHED:
      raise Exception('Not possible to change a finished step')

    action.check_error = check



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
  execute_remote : bool | None
    * ``None``: Default from stage will be taken
    * ``True``: Execution will be done on remote system (via SSH)
    * ``False``: Execution will be done on local system
  """

  id :int = 0


  def __init__(self, cmd: str=None, sequence: int=None, status: Cmd_Status=Cmd_Status.NEW,  
    environment: Command_Type=Command_Type.QSYS, stage: str=None, processing_step: str=None, 
    check_error: bool=True, dict: dict=None, id: int=None, run_in_new_job: bool=False, execute_remote: bool=None):

    self.id :int = id
    self.sequence :int = sequence
    self.environment :Command_Type = environment
    self.cmd :str = cmd
    self.stage = stage
    self.status = status
    self.run_in_new_job = run_in_new_job
    self.execute_remote = execute_remote
    self.run_history = rh.Run_History_List_list()
    self.check_error = check_error
    self.sub_actions = Deploy_Action_List_list()

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

    if self.id is None:
      self.id = Deploy_Action.get_next_id()


  def get_next_id() -> int:
    Deploy_Action.id += 1
    return Deploy_Action.id


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

    if self.sub_actions is None:
      self.sub_actions = Deploy_Action_List_list()
      
    if type(self.sub_actions) != Deploy_Action_List_list:
      sub_actions_list = self.sub_actions
      self.sub_actions = Deploy_Action_List_list()
      for sa in sub_actions_list:
        self.sub_actions.add_actions_from_dict(sa)




  def get_action_from_dict(dict: dict={}):

    action = Deploy_Action()

    for k, v in dict.items():
      setattr(action, k, v)

    if action.id == None:
      action.id = Deploy_Action.get_next_id()

    action.validate()

    return action




  def get_dict(self) -> dict:
    return {
      'id': self.id,
      'sequence': self.sequence, 
      'cmd': self.cmd,
      'status': self.status.value,
     # 'stage': self.stage.name,
      'stage': self.stage,
      'processing_step': self.processing_step,
      'environment': self.environment.value,
      'run_in_new_job': self.run_in_new_job,
      'execute_remote': self.execute_remote,
      'run_history': self.run_history.get_list(),
      'sub_actions': self.sub_actions.get_list(),
      'check_error': self.check_error
      }



  def __eq__(self, o):
    if (self.id, self.sequence, self.environment, self.cmd, self.stage, self.status, self.run_history, self.check_error, self.processing_step, self.run_in_new_job, self.execute_remote) == \
       (o.id, o.sequence, o.environment, o.cmd, o.stage, o.status, o.run_history, o.check_error, o.processing_step, o.run_in_new_job, o.execute_remote):
      return True

    logging.warn(f"{self.id=} - {self.sequence=} - {self.environment=} - {self.cmd=} - {self.stage=} - {self.status=} - {self.run_history=} - {self.check_error=} - {self.processing_step=} - {self.run_in_new_job=} - {self.execute_remote=}")
    logging.warn(f"{o.id=} - {o.sequence=} - {o.environment=} - {o.cmd=} - {o.stage=} - {o.status=} - {o.run_history=} - {o.check_error=} - {o.processing_step=} {o.run_in_new_job=} - {o.execute_remote=}")
    return False