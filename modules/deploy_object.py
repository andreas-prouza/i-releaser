import logging

from modules import deploy_action as da
from modules import workflow
from modules.object_status import Status as Obj_Status



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


  def __init__(self, level=0, prod_lib='', lib='', name='', type='', attribute='', dict=None):

    self.id: int|None = None
    self.meta_file_id: int|None = None
    self.level: int = level
    self.ready = True
    self.deploy_status = Obj_Status.NEW
    self.actions = da.Deploy_Action_List_list()
    self.depends_on = Deploy_Object_List()

    if dict is not None and len(dict) > 0:

      self.id = dict.get('id', None)
      self.meta_file_id = dict.get('meta_file_id', None)
      self.level = dict.get('level', None)
      self.ready = dict.get('ready', True)
      self.prod_lib = dict['prod_lib'].lower()
      self.lib = dict['lib'].lower()
      self.name = dict['name'].lower()
      self.type = dict['type'].lower()
      self.attribute = dict['attribute'].lower()
      self.deploy_status = Obj_Status(dict['deploy_status'])

      if len(dict.get('actions', [])) > 0:
        for action in dict['actions']:
          self.actions.add_actions_from_dict(action)
          #self.actions.add_action(da.Deploy_Action(dict_data=action))
      
      if len(dict.get('depends_on', [])) > 0:
        for obj in dict['depends_on']:
          self.depends_on.add_object(Deploy_Object(dict=obj))
      return
 
    self.prod_lib = prod_lib.lower()
    self.lib = lib.lower()
    self.name = name.lower()
    self.type = type.lower()
    self.attribute = attribute.lower()

    if self.attribute is None or self.attribute == '':
      raise Exception(f'No attribute was set for {self.lib}/{self.name} ({self.type})')



  def get_dict(self) -> dict:
    return {
      'id' : self.id,
      'meta_file_id' : self.meta_file_id,
      'level' : self.level,
      'ready' : self.ready,
      'lib' : self.lib,
      'prod_lib' : self.prod_lib,
      'name' : self.name,
      'type' : self.type,
      'attribute' : self.attribute,
      'deploy_status' : self.deploy_status.value,
      'actions' : self.actions.get_actions_as_dict(),
      'depends_on' : self.depends_on.get_objects_as_dict()
    }


  def __eq__(self, o):
    if (self.ready, self.lib, self.prod_lib, self.name, self.type, self.attribute, self.deploy_status, self.actions, self.depends_on) == \
       (o.ready, o.lib, o.prod_lib, o.name, o.type, o.attribute, o.deploy_status, o.actions, o.depends_on):
      return True

    logging.warning(f"{self.ready} - {self.lib} - {self.prod_lib} - {self.name} - {self.type} - {self.attribute} - {self.deploy_status} - {self.actions} - {self.depends_on}")
    logging.warning(f"{o.ready} - {o.lib} - {o.prod_lib} - {o.name} - {o.type} - {o.attribute} - {o.deploy_status} - {o.actions} - {o.depends_on}")

    return False
  





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



  def add_objects(self, objects: 'Deploy_Object_List'):
    
    self.extend(objects.get_objects_as_list())


  def add_object(self, objects: Deploy_Object):
    
    self.append(objects)



  def sort_objects(self):
    def get_sorted_object_list_value(obj):
      return obj.lib + obj.type + obj.name

    #self.sort(key=get_sorted_object_list_value)



  def get_objects_as_list(self) -> list[Deploy_Object]:
    #self.sort_objects()
    return self



  def get_objects_as_dict(self, processing_step: str=None, stage: str=None) -> list[dict]: 

    #self.sort_objects()
    objs = []

    for obj in self:
      if processing_step is None or obj.processing_step == processing_step:
        # Consider stage if given
        if stage is not None and obj.stage.name is not None and stage != obj.stage.name:
          continue
        objs.append(obj.get_dict())

    return objs



  def get_lib_list(self) -> list[str]:
    libs = []
    for o in self:
      if o.lib not in libs:
        libs.append(o.lib)
    libs.sort()
    return libs


  def get_lib_list_with_prod_lib(self, ready: bool=None) -> list[dict]:
    libs = []
    lib_list = []
    for o in self:
      if (ready is None or o.ready == ready) and o.lib not in lib_list:
        lib_list.append(o.lib)
        libs.append({'lib' : o.lib, 'prod_lib': o.prod_lib})
    return libs



  def get_lib_list_from_prod(self, ready: bool=None) -> list[str]:
    libs = []
    for o in self:
      if (ready is None or o.ready == ready) and o.prod_lib not in libs:
        libs.append(o.prod_lib)
    return libs



  def get_obj_list_by_lib(self, lib, ready: bool=None) -> list[Deploy_Object]:
    objs = []
    for o in self:
      if o.prod_lib == lib and (o.ready == ready or ready is None):
        objs.append(o)
    return objs



  def get_obj_list_by_prod_lib(self, lib, ready: bool=None) -> list[Deploy_Object]:
    objs = []
    for o in self:
      if o.prod_lib == lib and (o.ready == ready or ready is None):
        objs.append(o)
    return objs



  def get_prod_object(self, prod_lib: str, name: str, type: str, ready: bool=None) -> Deploy_Object|None:
    for o in self:
      if o.prod_lib == prod_lib and o.type == type and o.name == name and (o.ready == ready or ready is None):
        return o
    logging.warning(f"No prod object found for {prod_lib=}, {name=}, {type=}")
    return None


  def get_deploy_object(self, lib: str, name: str, type: str) -> Deploy_Object|None:
    for o in self:
      if o.lib == lib and o.type == type and o.name == name:
        return o
    logging.warning(f"No deploy object found for {lib=}, {name=}, {type=}")
    return None



  def add_object_action(self, lib: str, name: str, type: str, action: type[da.Deploy_Action]):

    if type(action) == str:
      action = da.Deploy_Action(cmd=action)

    obj = self.get_prod_object(lib, name, type)
    obj.actions.add_action(action)



#  def load_actions_from_json(self, file: str, stages: []=[]):
#    obj_cmds = []

#    with open(file, "r") as file:
#      obj_cmds = json.load(file)

#    for stage in stages:
#      for oc in obj_cmds:
#        self.add_object_action_from_dict(oc)



  def add_object_action_from_dict(self, dict: dict, workflow: workflow.Workflow):
    
    obj = self.get_prod_object(dict.get('lib', ''), dict.get('name', ''), dict.get('type', ''))
    
    if obj is None:
      return
    
    for a in dict['actions']:

      if 'stages' not in a.keys() or a['stages'] is None or a['stages'] == []:
        # Do it for all stages
        a['stages'] = workflow.stages

      stages = a['stages']
      del a['stages']
      
      for stage in stages:
        action = da.Deploy_Action(dict_data=a, stage=stage['name'])
        obj.actions.add_action(action)



  def get_actions(self, processing_step: str=None, stage: str=None, action_id: int=None, include_subactions: bool=False):

    if type(stage) != str:
      raise Exception(f"Stage is not a string")
      
    list: list[da.Deploy_Action]=[]

    for do in self:
      list.append(do.actions.get_actions(processing_step=processing_step, stage=stage, action_id=action_id, include_subactions=include_subactions))

    return list



  def get_actions_as_dict(self, processing_step: str=None, stage: str=None):

    list=[]

    for a in self.get_actions(processing_step, stage):
      list.append(a.get_dict())

    return list



  def set_objects_status(self, status: Obj_Status):
    for o in self:
      if o.ready:
        o.deploy_status = status



  def get_layered_objects(self) -> list['Deploy_Object_List']:
    """
    Organizes the list of deployment objects into layers based on their dependencies.

    Returns:
        A list of Deploy_Object_List, where each list is a layer.
    """
    
    # Create a dictionary for quick lookup of objects by their properties
    objects_dict = {(obj.lib, obj.name, obj.type): obj for obj in self}
    
    # Initialize layers
    layers: list[Deploy_Object_List] = []
    
    # Set of processed objects
    processed_objects = set()
    
    while len(processed_objects) < len(self):
        current_layer = Deploy_Object_List()
        
        for obj in self:
            obj_key = (obj.lib, obj.name, obj.type)
            
            if obj_key in processed_objects:
                continue
            
            # Check if all dependencies are met
            dependencies_met = True
            if obj.depends_on:
                for dep in obj.depends_on:
                    dep_key = (dep.lib, dep.name, dep.type)
                    if dep_key not in processed_objects:
                        dependencies_met = False
                        break
            
            if dependencies_met:
                current_layer.append(obj)
        
        if not current_layer:
            # Break to avoid infinite loop in case of circular dependencies
            # You might want to add more sophisticated error handling here
            logging.error("Circular dependency detected or missing dependencies.")
            
            # Add remaining objects to a final layer to at least display them
            remaining_objects = Deploy_Object_List()
            for obj in self:
                if (obj.lib, obj.name, obj.type) not in processed_objects:
                    remaining_objects.append(obj)

            if remaining_objects:
                layers.append(remaining_objects)
            break

        layers.append(current_layer)
        
        for obj in current_layer:
            processed_objects.add((obj.lib, obj.name, obj.type))
            
    return layers




