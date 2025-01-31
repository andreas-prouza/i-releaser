from __future__ import annotations
import os
import datetime
import logging
from enum import Enum
from io import StringIO

from etc import constants
from modules import meta_file, stages as st
from modules.cmd_status import Status as Cmd_Status




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



    def add_history(self, history: type[Meta_File_History]=None) -> None:
        if type(history) != Meta_File_History:
            raise Exception(f"Parameter type {type(history)} does not match Meta_File_History")

        self.append(history)



    def add_historys_from_list(self, list: []):

        for a in list:
            history = Meta_File_History(dict=a)
            self.add_history(history)



    def get_list(self) -> []:

        list = []

        for h in self:
            list.append(h.get_dict())

        return list







class Meta_File_History:
    """
    History of executed commands (runs)

    Parameters
    ----------
    timestamp : datetime
    log : StringIO
    """



    def __init__(self, log: StringIO=None, create_time=None, dict: {}={}):
        self.log = log
        self.create_time = create_time

        if self.create_time == None:
            self.create_time = str(datetime.datetime.now())
            #self.create_time = '2023-03-04 14:31:30.404775'

        if len(dict) > 0 and len(list(set(dict.keys()) - set(self.__dict__.keys()))) == 0:
            for k, v in dict.items():
                setattr(self, k, v)


    def get_dict(self) -> {}:

        dict={'create_time': self.create_time}
        dict['log']= self.log
        if type(self.log) == StringIO:
            dict['log']= self.log.getvalue()
        return dict



    def __eq__(self, o):
        if (self.create_time, self.log) == \
               (o.create_time, o.log):
            return True
        return False
