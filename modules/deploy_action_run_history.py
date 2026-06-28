import datetime
import logging


class Deploy_Action_Run_History:

  def __init__(self, status: str=None, stdout: str=None, stderr: str=None, create_time: str=None, dict: dict=None, id: int=None):

    self.id = id
    self.status = status
    self.stdout = stdout
    self.stderr = stderr
    self.create_time = create_time

    if self.create_time is None:
      self.create_time = str(datetime.datetime.now())

    if dict is not None:
      for key in self.__dict__:
        if key in dict:
          self.__setattr__(key, dict[key])


  def get_dict(self) -> dict:
    return {
      'id': self.id,
      'status': self.status,
      'stdout': self.stdout,
      'stderr': self.stderr,
      'create_time': self.create_time
      }


  def __eq__(self, o):
    if (self.id, self.status, self.stdout, self.stderr, self.create_time) == \
       (o.id, o.status, o.stdout, o.stderr, o.create_time):
      return True
    
    logging.warning(f"{self.id=} - {self.status=} - {self.stdout=} - {self.stderr=} - {self.create_time=}")
    logging.warning(f"{o.id=} - {o.status=} - {o.stdout=} - {o.stderr=} - {o.create_time=}")
    return False



class Deploy_Action_Run_History_List(list):

    def __init__(self, iterable=None):

        if iterable is not None:
            super().__init__(self._validate_number(item) for item in iterable)
        else:
            super().__init__()

    def __setitem__(self, index, item):
        super().__setitem__(index, self._validate_number(item))

    def insert(self, index, item):
        super().insert(index, self._validate_number(item))

    def append(self, item):
        super().append(self._validate_number(item))

    def extend(self, other):
        if isinstance(other, type(Deploy_Action_Run_History)):
            super().extend(other)
        else:
            super().extend(self._validate_number(item) for item in other)

    def _validate_number(self, value):
        if type(value) == Deploy_Action_Run_History:
            return value
        raise TypeError(
            f"Deploy_Action_Run_History value expected, got {type(value).__name__}"
        )

    def get_list(self) -> list[dict]:
        list = []
        for a in self:
            list.append(a.get_dict())
        return list

    def add_historys_from_list(self, history_list: list[dict]):
        for item in history_list:
            self.append(Deploy_Action_Run_History(dict=item))
