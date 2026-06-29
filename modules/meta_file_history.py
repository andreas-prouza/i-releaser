import datetime
from io import StringIO





class Meta_File_History:
  """       
  History of executed commands (runs)

  Parameters
  ----------
  timestamp : datetime
  log : StringIO
  """



  def __init__(self, id:int=None, log: StringIO=None, create_time=None, meta_file_id: int=None, dict: dict=None):
    self.id: int = id
    self.log = log
    self.create_time = create_time
    self.meta_file_id = meta_file_id

    if self.create_time == None:
        self.create_time = str(datetime.datetime.now())
        #self.create_time = '2023-03-04 14:31:30.404775'

    if dict is not None and len(dict) > 0 and len(list(set(dict.keys()) - set(self.__dict__.keys()))) == 0:
      for k, v in dict.items():
        setattr(self, k, v)


  def get_dict(self) -> dict:

    dict={'create_time': self.create_time}
    dict['log']= self.log
    dict['id']= self.id
    if type(self.log) == StringIO:
      dict['log']= self.log.getvalue()
    return dict



  def __eq__(self, o):
    if (self.create_time, self.log) == \
           (o.create_time, o.log):
      return True
    return False
  




class Meta_File_History_List_list(list):
    def __init__(self):
        super().__init__()

    def __setitem__(self, index, item):
        super().__setitem__(index, self._validate_item(item))

    def insert(self, index, item):
        super().insert(index, self._validate_item(item))

    def append(self, item):
        super().append(self._validate_item(item))

    def extend(self, other):
        if isinstance(other, type(Meta_File_History)):
            super().extend(other)
        else:
            super().extend(self._validate_item(item) for item in other)

    def _validate_item(self, value):
        if type(value) == Meta_File_History:
            return value
        raise TypeError(
            f"Meta_File_History value expected, got {type(value).__name__}"
        )



    def add_history(self, history: Meta_File_History=None) -> None:
      if type(history) != Meta_File_History:
        raise Exception(f"Parameter type {type(history)} does not match Meta_File_History")

      self.append(history)



    def add_historys_from_list(self, list: list) -> None:

      for a in list:
        history = Meta_File_History(dict=a)
        self.add_history(history)



    def get_list(self) -> list:

      list = []

      for h in self:
        list.append(h.get_dict())

      return list

