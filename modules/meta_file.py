from __future__ import annotations
import datetime
import json
import configparser
import logging
import re
import os

from etc import logger_config, constants
from modules import deploy_action as da
from modules import deploy_object as do
from modules import stages as s





class Meta_File:


    def __init__(self, file_name=None, create_time=None, deploy_version : int=None, current_stages: []=["START"]):

      self.deploy_version = deploy_version
      if deploy_version == None:
        self.deploy_version = Meta_File.get_next_deploy_version()
      
      self.status = 'new'

      self.create_time = create_time

      if self.create_time == None:
        self.create_time = str(datetime.datetime.utcnow())

      self.create_date = re.sub(" .*", '', self.create_time)

      self.file_name = file_name
      if self.file_name == None:
        self.file_name = constants.C_DEPLOY_META_FILE
      self.file_name = self.file_name.format(**self.__dict__)

      self.current_stages = s.Stage_List_list(current_stages)
      self.object_libs = []
      self.deploy_objects = do.Deploy_Object_List()
      self.backup_deploy_lib = None
      self.main_deploy_lib = None

      self.set_deploy_main_lib(f"d{str(self.deploy_version).zfill(9)}")
      self.set_deploy_backup_lib(f"b{str(self.deploy_version).zfill(9)}")

      self.actions = da.Deploy_Action_List()

      self.write_meta_file()



    def get_next_deploy_version():

        with open(constants.C_DEPLOY_VERSION, "r") as file:
            versions_config = json.load(file)

        version = versions_config['versions']['last_deploy_version'] + 1
        versions_config['versions']['last_deploy_version'] = version

        with open(constants.C_DEPLOY_VERSION, 'w') as file:
            json.dump(versions_config, file)

        return version



    def set_next_stage(self, from_stage: str):

      with open(constants.C_STAGES, "r") as file:
          stages_json = json.load(file)

      if from_stage not in self.current_stages.get_all_names():
        raise Exception(f"Stage {from_stage} ist not in the list of current stages: {self.current_stages.get_all_names()}")

      for sj in stages_json:
        if from_stage == sj['name']:
          self.current_stages.remove_stage(from_stage)
          for next_stage in sj['next_stages']:
            self.current_stages.append(s.Stage.get_stage(next_stage))

          return

      raise Exception(f"Stage {from_stage} ist not in the list of current stages: {self.current_stages.get_all_names()}")



    def set_deploy_main_lib(self, library):
      self.main_deploy_lib = library.lower()



    def set_deploy_backup_lib(self, library):
      self.backup_deploy_lib = library.lower()



    def set_object_libs(self, libraries):

      self.object_libs = libraries



    def add_deploy_object(self, object: type[do.Deploy_Object]):

      self.deploy_objects.add_object(object)



    def is_backup_name_already_in_use(self, obj_lib: str, obj_name: str, backup_name: str, obj_type: str):
      """
      Parameters
      ----------
      obj_lib : str
          Library name from asking object
      obj_name : str
          Object name from asking object
      backup_name : str, optional
          Suggested backup name which needs to be checked for uniqueness  
      ----------
      """

      for lib in self.deploy_objects:
        for obj in self.deploy_objects[lib]:
          # Check if back-up name is already in use
          if obj['obj_type'] == obj_type and obj.get('backup_name', '') == backup_name:
            return True
          
          # Check if back-up name is already used as object name
          if (not (lib == obj_lib and 
                  obj['obj_type'] == obj_type and 
                  obj['obj_name'] == obj_name) and 
             obj['obj_type'] == obj_type and 
             obj['obj_name'] == backup_name):
            return True

      return False



    def set_deploy_objects(self, objects: []):

      for obj in objects:
        self.add_deploy_object(do.Deploy_Object(dict=obj))



    def get_actions(self, processing_step: str=None, stage: str=None):

      list=[]

      for a in self.actions.actions:
        if processing_step is None or a.processing_step == processing_step:
          # Consider stage if given
          if a.stage is not None and type(a.stage) != s.Stage:
            raise Exception("Stage is not an object!")
        
          if stage is not None and a.stage.name is not None and stage != a.stage.name:
            continue
          list.append(a)
      
     # list = list + self.deploy_objects.get_actions(processing_step=processing_step, stage=stage)

      return list



    def get_actions_as_dict(self, processing_step: str=None, stage: str=None):

      return self.actions.get_actions_as_dict(processing_step=processing_step, stage=stage)



    def load_json_file(file_name: str) -> Meta_File:

      with open (file_name, "r") as file:
        meta_file_json=json.load(file)
        meta_file = Meta_File(deploy_version=meta_file_json['general']['deploy_version'],
                              file_name=meta_file_json['general']['file_name'],
                              create_time=meta_file_json['general']['create_time'],
                              current_stages=s.Stage_List_list(meta_file_json['general']['current_stages']),
                             )
        meta_file.set_deploy_objects(meta_file_json['objects'])
        meta_file.set_deploy_main_lib(meta_file_json['deploy_libs']['main_lib'])
        meta_file.set_deploy_backup_lib(meta_file_json['deploy_libs']['backup_lib'])
        meta_file.actions.add_actions_from_list(meta_file_json['deploy_cmds'])
        meta_file.write_meta_file()

        return meta_file



    def get_all_data_as_dict(self) -> {}:

      list = {}
      list['general'] = {'deploy_version':  self.deploy_version,
                         'file_name':       self.file_name,
                         'create_time':     self.create_time,
                         'update_time':     datetime.datetime.utcnow(),
                         'status':          self.status,
                         'current_stages':  self.current_stages.get_dict()
                        }
      list['deploy_libs'] = {'main_lib':    self.main_deploy_lib,
                             'backup_lib':  self.backup_deploy_lib,
                             'object_libs': self.deploy_objects.get_lib_list()
                            }
      list['deploy_cmds'] = self.get_actions_as_dict()
      list['objects'] = self.deploy_objects.get_objectjs_as_dict()

      return list



    def write_meta_file(self):

      file_dir = os.path.dirname(os.path.realpath(self.file_name))
      if not os.path.isdir(file_dir):
        os.makedirs(file_dir)

      with open(self.file_name, 'w') as file:
        json.dump(self.get_all_data_as_dict(), file, default=str, indent=4)



    def add_object_from_meta_structure(self, objects: [], object_type: str):

      for obj in objects:

          if '/' not in obj:
              continue

          obj = obj.split('/')
          deploy_obj = do.Deploy_Object(lib=obj[0], name=obj[1], type=object_type)

          self.add_deploy_object(deploy_obj)



    def import_objects_from_config_file_old(self, config_file: str):

      object_config = configparser.ConfigParser()
      object_config.read(config_file, encoding='UTF-8')

      obj_list = dict(object_config.items('OBJECTS'))
      for obj_type in obj_list:
          self.add_object_from_meta_structure(obj_list[obj_type].split(' '), obj_type)

      self.write_meta_file()


    def import_objects_from_config_file(self, config_file: str):

      with open(config_file, "r") as file:
        for line in file:
          tmp = line.lower().rstrip('\r\n').rstrip('\n').split('|')
          prod_obj = re.split(r"/|\.", tmp[1])
          target_obj = tmp[2].split('/')
          obj = do.Deploy_Object(lib=target_obj[0], prod_lib=prod_obj[0], name=prod_obj[1], type=prod_obj[3], attribute=prod_obj[2])
          self.add_deploy_object(obj)



    def load_actions_from_json(self, file: str):
      obj_cmds = []

      with open(file, "r") as file:
        obj_cmds = json.load(file)

      for stage in self.current_stages.get_all_names():
        for oc in obj_cmds:
          self.deploy_objects.add_object_action_from_dict(dict=oc, stage=stage)
      
      self.write_meta_file()

