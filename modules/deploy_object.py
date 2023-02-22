from __future__ import annotations
import json
import logging

from modules import deploy_action as da


class Deploy_Object_List:


  def __init__(self):
    self.dol = []



  def add_objects(self, objects: type[da.Deploy_Object_List]):
    
    self.dol = self.dol + objects.get_objectjs_as_list()



  def add_object(self, objects: type[Deploy_Object]):
    
    self.dol.append(objects)



  def sort_objects(self):
    def get_sorted_object_list_value(obj):
      return obj.lib + obj.type + obj.name

    self.dol.sort(key=get_sorted_object_list_value)



  def get_objectjs_as_list(self) -> []: 
    self.sort_objects()
    return self.dol



  def get_objectjs_as_dict(self) -> []: 
    self.sort_objects()
    objs = []

    for obj in self.dol:
      objs.append(obj.get_dict())
    return objs



  def get_lib_list(self) -> []:
    libs = []
    for o in self.dol:
      if o.lib not in libs:
        libs.append(o.lib)
    libs.sort()
    return libs



  def get_obj_list_by_lib(self, lib) -> [Deploy_Object]:
    objs = []
    for o in self.dol:
      if o.lib == lib:
        objs.append(o)
    return objs



  def get_object(self, obj_lib: str, obj_name: str, obj_type: str) -> Deploy_Object:
    for o in self.dol:
      if o.lib == obj_lib and o.type == obj_type and o.name == obj_name:
        return o
    return None



  def add_object_action(self, obj_lib: str, obj_name: str, obj_type: str, action: type[da.Deploy_Action]):

    if type(action) == str:
      action = da.Deploy_Action(cmd=action)

    obj = self.get_object(obj_lib, obj_name, obj_type)
    obj.actions.add_action(action)



  def load_actions_from_json(self, file : str):
    with open(file, "r") as file:
      obj_cmds = json.load(file)
      for oc in obj_cmds:
        self.add_object_action_from_dict(oc)



  def add_object_action_from_dict(self, dict: {}):
    
    obj = self.get_object(dict['obj_lib'], dict['obj_name'], dict['obj_type'])
    
    for a in dict['actions']:
      action = da.Deploy_Action(dict=a)
      obj.actions.add_action(action)




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


  def __init__(self, lib='', name='', type='', dict={}):

    self.deploy_status = 'in preperation'
    self.actions = da.Deploy_Action_List()

    if len(dict) > 0:

      self.lib = dict['obj_lib'].lower()
      self.name = dict['obj_name'].lower()
      self.type = dict['obj_type'].lower()

      if len(dict['actions']) > 0:
        for a in dict['actions']:
          self.actions.add_action(da.Deploy_Action(dict=a))
      return

    self.lib = lib.lower()
    self.name = name.lower()
    self.type = type.lower()
    #self.backup_name = ''  # Nicht nötig, da alle Objekte in ein SAVF je Lib gespeichert werden.



  def get_dict(self) -> {}:
    return {
      'obj_lib' : self.lib,
      'obj_name' : self.name,
      'obj_type' : self.type,
      'deploy_status' : self.deploy_status,
      'actions' : self.actions.get_list()
    }


