from __future__ import annotations
import json
import logging

from modules import deploy_action as da
from etc import constants



class Deploy_Object_List(list):
  def __init__(self):
      super().__init__()

  def __setitem__(self, index, item):
      super().__setitem__(index, self._validate_number(item))

  def insert(self, index, item):
      super().insert(index, self._validate_number(item))

  def append(self, item):
      super().append(self._validate_number(item))

  def extend(self, other):
      if isinstance(other, type(Deploy_Object)):
          super().extend(other)
      else:
          super().extend(self._validate_number(item) for item in other)

  def _validate_number(self, value):
      if type(value) == Deploy_Object:
          return value
      raise TypeError(
          f"Deploy_Object value expected, got {type(value).__name__}"
      )



  def add_objects(self, objects: type[da.Deploy_Object_List]):
    
    self = self + objects.get_objectjs_as_list()


  def add_object(self, objects: type[Deploy_Object]):
    
    self.append(objects)



  def sort_objects(self):
    def get_sorted_object_list_value(obj):
      return obj.lib + obj.type + obj.name

    #self.sort(key=get_sorted_object_list_value)



  def get_objectjs_as_list(self) -> []: 
    #self.sort_objects()
    return self



  def get_objectjs_as_dict(self, processing_step: str=None, stage: str=None) -> []: 

    #self.sort_objects()
    objs = []

    for obj in self:
      if processing_step is None or obj.processing_step == processing_step:
        # Consider stage if given
        if stage is not None and a.stage.name is not None and stage != a.stage.name:
          continue
        objs.append(obj.get_dict())

    return objs



  def get_lib_list(self) -> []:
    libs = []
    for o in self:
      if o.lib not in libs:
        libs.append(o.lib)
    libs.sort()
    return libs


  def get_lib_list_with_prod_lib(self) -> {}:
    libs = []
    lib_list = []
    for o in self:
      if o.lib not in lib_list:
        lib_list.append(o.lib)
        libs.append({'lib' : o.lib, 'prod_lib': o.prod_lib})
    return libs



  def get_lib_list_from_prod(self) -> {}:
    libs = []
    for o in self:
      if o.prod_lib not in libs:
        libs.append(o.prod_lib)
    return libs



  def get_obj_list_by_lib(self, lib) -> [Deploy_Object]:
    objs = []
    for o in self:
      if o.lib == lib:
        objs.append(o)
    return objs



  def get_obj_list_by_prod_lib(self, lib) -> [Deploy_Object]:
    objs = []
    for o in self:
      if o.prod_lib == lib:
        objs.append(o)
    return objs



  def get_object(self, obj_lib: str, obj_name: str, obj_type: str) -> Deploy_Object:
    for o in self:
      if o.lib == obj_lib and o.type == obj_type and o.name == obj_name:
        return o
    return None



  def add_object_action(self, obj_lib: str, obj_name: str, obj_type: str, action: type[da.Deploy_Action]):

    if type(action) == str:
      action = da.Deploy_Action(cmd=action)

    obj = self.get_object(obj_lib, obj_name, obj_type)
    obj.actions.add_action(action)



#  def load_actions_from_json(self, file: str, stages: []=[]):
#    obj_cmds = []

#    with open(file, "r") as file:
#      obj_cmds = json.load(file)

#    for stage in stages:
#      for oc in obj_cmds:
#        self.add_object_action_from_dict(oc)



  def add_object_action_from_dict(self, stage: str=None, dict: {}={}):
    
    if stage is None:
      raise Exception(f"No stage was given for {dict}")

    obj = self.get_object(dict['obj_lib'], dict['obj_name'], dict['obj_type'])
    
    if obj is None:
      return

    for a in dict['actions']:
      if 'stages' not in a.keys() or a['stages'] is None or a['stages'] == [] or stage in a['stages']:
        if 'stages' in a.keys():
          del a['stages']
        action = da.Deploy_Action(dict=a, stage=stage)
        obj.actions.add_action(action)



  def get_actions(self, processing_step: str=None, stage: str=None):

    list=[]

    for do in self:
      for a in do.actions:
        if processing_step is None or a.processing_step == processing_step:
          # Consider stage if given
          if stage is not None and a.stage is not None and stage != a.stage:
            continue
          list.append(a)

    return list


  def get_actions_as_dict(self, processing_step: str=None, stage: str=None):

    list=[]

    for a in self.get_actions(processing_step, stage):
      list.append(a.get_dict())

    return list





class Deploy_Object:
  """Stored information of an object for deployment
  Attributes
  ----------
  lib : str
      Library Name of the object
  name : str
      Object name
  type : str
      Object type (``*FILE``, ``*PGM``, ``*SRVPGM``, ...)
  deploy_status : str
      Current status of the deployment
      * ``in preperation``
      * ``ready to transfer to target system``
      * ``transfered to target system``
      * ``deployment in process``
      * ``deployment failed``
      * ``ready for retry``
      * ``deployment finished successfully``
  actions_
  ----------
  """


  def __init__(self, prod_lib='', lib='', name='', type='', attribute='', dict={}):

    self.deploy_status = 'in preperation'
    self.actions = da.Deploy_Action_List_list()

    if len(dict) > 0:

      self.prod_lib = dict['obj_prod_lib'].lower()
      self.lib = dict['obj_lib'].lower()
      self.name = dict['obj_name'].lower()
      self.type = dict['obj_type'].lower()
      self.attribute = dict['obj_attribute'].lower()

      if len(dict['actions']) > 0:
        for key_stages in dict['actions'].keys():
          for cmd in dict['actions'][key_stages]:
            self.actions.add_action(da.Deploy_Action(dict=cmd))
      return

    self.prod_lib = prod_lib.lower()
    self.lib = lib.lower()
    self.name = name.lower()
    self.type = type.lower()
    self.attribute = attribute.lower()

    if self.attribute is None or self.attribute == '':
      raise Exception(f'No attribute was set for {self.lib}/{self.name} ({self.type})')



  def get_dict(self) -> {}:
    return {
      'obj_lib' : self.lib,
      'obj_prod_lib' : self.prod_lib,
      'obj_name' : self.name,
      'obj_type' : self.type,
      'obj_attribute' : self.attribute,
      'deploy_status' : self.deploy_status,
      'actions' : self.actions.get_actions_as_dict()
    }


  def __eq__(self, o):
    if (self.lib, self.prod_lib, self.name, self.type, self.attribute, self.deploy_status, self.actions) == (o.lib, o.prod_lib, o.name, o.type, o.attribute, o.deploy_status, o.actions):
      return True
    return False