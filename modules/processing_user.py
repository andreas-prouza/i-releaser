import datetime
import logging

from modules.action_type import Action_type
from modules import meta_file as mf


class Processing_User:
  def __init__(self, id: int=None, meta_file_id: int=None, action: Action_type=None, timestamp: datetime.datetime=None, stage: str=None, details:str=None, dict: dict=None):

    self.id :int = id
    self.meta_file_id: int = meta_file_id
    self.action: Action_type = action
    self.user: str = mf.Meta_File.CURRENT_USER
    self.timestamp: datetime.datetime = timestamp
    self.stage: str = stage
    self.details: str = details

    if dict is not None and len(list(set(dict.keys()) - set(self.__dict__.keys()))) == 0:
      
      for k, v in dict.items():

        setattr(self, k, v)





  def get_processing_user_from_dict(dict: dict={}):

    pu = Processing_User()

    for k, v in dict.items():
      setattr(pu, k, v)

    return pu




  def get_dict(self) -> dict:
    return {
      'id': self.id,
      'action': self.action.value if self.action else None,
      'user': self.user,
      'timestamp': self.timestamp.isoformat() if self.timestamp else None,
      'stage': self.stage,
      'details': self.details
      }

