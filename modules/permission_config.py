import logging
import time
from typing import Dict, List
from fastapi import Request

from etc import constants, constants
from modules import files, meta_file, permissions
from modules.db import stage_data





def check_user_permission(action : permissions.PermissionAction, workflow:str|None =None, stage:str|None = None, stage_id:int|None =None):

  user = meta_file.Meta_File.CURRENT_USER.lower() if meta_file.Meta_File.CURRENT_USER else None

  if not is_user_allowed(user, action, workflow, stage, stage_id):
      error = Exception(f"User {user} does not have permission {action} (workflow: {workflow}, stage: {stage or stage_id})")
      logging.exception(error, stack_info=True)
      raise error





def is_user_allowed(user, action : permissions.PermissionAction, workflow:str|None =None, stage:str|None =None, stage_id:int|None =None):
  
  if user is None:
    logging.warning("User is None")
    return False
  
  user = user.lower()
  if workflow is not None:
    workflow = workflow.lower()

  if stage is None and stage_id is not None:
    stage_obj = stage_data.get_stage(stage_id)
    stage = stage_obj.name if stage_obj is not None else None
    

  logging.debug(f"Check if user {user} has permission {action} ({workflow=}, {stage or stage_id=})")

  if user not in PermissionKonfig.get_user_list():
    logging.info(f"{user=} is not in list: {PermissionKonfig.get_user_list()}")
    return False

  current_permission: permissions.User = PermissionKonfig.get_user_permissions(user)

  if is_permission_allowed(current_permission.permissions, action, workflow, stage):
    logging.debug(f"User {user} has permission {action} (workflow: {workflow}, stage: {stage})")
    return True

  for role in current_permission.roles:
    role_permission = PermissionKonfig.role_permissions.get(role, permissions.Role())
    if is_permission_allowed(role_permission.permissions, action, workflow, stage):
      logging.debug(f"User {user} has permission {action} through role {role} (workflow: {workflow}, stage: {stage})")
      return True
    
  logging.info(f"User {user} does not have permission {action} (workflow: {workflow}, stage: {stage})")
  return False



def is_permission_allowed(current_permission: permissions.Permissions, action : permissions.PermissionAction, workflow=None, stage=None):

  if action in current_permission.general:
    return True

  if workflow is not None and workflow in current_permission.workflows:
    current_wf: dict = current_permission.workflows[workflow]

    if permissions.PermissionAction(action) in current_wf['general']:
      return True

    if stage is not None and stage.lower() in current_wf['stages']:
      current_stage = current_wf['stages'][stage.lower()]

      if permissions.PermissionAction(action) in current_stage:
        return True

  return False








class PermissionKonfig:


  __last_loaded = 0
  __reload_interval = 2
  __file_hash = None
  
  allowed_users = []
  role_permissions: Dict[str, permissions.Role] = {}
  user_permissions: Dict[str, permissions.User] = {}


  @staticmethod
  def get_user_list() -> list[str]:

    PermissionKonfig.check_reload()
    return PermissionKonfig.allowed_users
  


  @staticmethod
  def get_user_permissions(user) -> permissions.User:

    PermissionKonfig.check_reload()
    return PermissionKonfig.user_permissions.get(user.lower(), permissions.User())
  


  @staticmethod
  def add_user_permission(name: str, roles: List[str]|None = None, general: List[permissions.PermissionAction]|None = None, workflows: Dict[str, permissions.PermissionWorkflow]|None = None, description='', mail='', extra={}, data: dict = {}):

    PermissionKonfig.check_reload()

    if name.lower() in PermissionKonfig.user_permissions.keys():
      error = Exception(f"User {name} already exists, overwriting permissions")
      logging.exception(error, stack_info=True)
      raise error

    perm: permissions.Permissions = permissions.Permissions(general=general or data.get('general', []), workflows=workflows or data.get('workflows', {}))
    PermissionKonfig.user_permissions[name.lower()] = permissions.User(permissions=perm, roles=roles or data.get('roles', []), detailed_infos=permissions.DetailedInfos(description=description or data.get('detailed_infos', {}).get('description', ''), mail=mail or data.get('detailed_infos', {}).get('mail', ''), extra=extra or data.get('detailed_infos', {}).get('extra', {})))
    if name.lower() not in PermissionKonfig.allowed_users:
      PermissionKonfig.allowed_users.append(name.lower())
      
    PermissionKonfig.save_permissions()
  




  @staticmethod
  def add_role_permission(name: str, general: List[str]|None = None, data: dict = {}):

    PermissionKonfig.check_reload()

    if name.lower() in PermissionKonfig.role_permissions.keys():
      error = Exception(f"Role {name} already exists, overwriting permissions")
      logging.exception(error, stack_info=True)
      raise error

    perm: permissions.Permissions = permissions.Permissions(general=general or data.get('general', []))
    PermissionKonfig.role_permissions[name.lower()] = permissions.Role(permissions=perm)

    PermissionKonfig.save_permissions()




  @staticmethod
  def save_permissions():

    data = {
      'users': PermissionKonfig.user_permissions,
      'roles': PermissionKonfig.role_permissions
    }

    files.writeJson(data, constants.C_USER_PERMISSIONS)




  @staticmethod
  def check_reload():
    
    current_time = time.time()

    if current_time - PermissionKonfig.__last_loaded > PermissionKonfig.__reload_interval:

      file_hash = files.get_file_hash(constants.C_USER_PERMISSIONS)

      if file_hash == PermissionKonfig.__file_hash:
        return

      data = files.getJson(constants.C_USER_PERMISSIONS, retry=True)
      
      if data is None:
        logging.warning(f"Could not load permissions from {constants.C_USER_PERMISSIONS}, file is empty or not valid json")
        return
  
      PermissionKonfig.user_permissions = data.get('users', {})
      PermissionKonfig.role_permissions = data.get('roles', {})

      # Convert string permissions to PermissionAction objects
      PermissionKonfig.convert_permissions('user', PermissionKonfig.user_permissions)
      PermissionKonfig.convert_permissions('role', PermissionKonfig.role_permissions)
      logging.debug(f"Reloaded user permissions: {PermissionKonfig.user_permissions}")
      logging.debug(f"Reloaded role permissions: {PermissionKonfig.role_permissions}")

      PermissionKonfig.allowed_users = list(PermissionKonfig.user_permissions.keys())
      PermissionKonfig.__file_hash = file_hash

      PermissionKonfig.__last_loaded = current_time



  @staticmethod
  def convert_permissions(type:str, user_permissions: dict):

    logging.debug(f"{user_permissions=}")
    for user, user_items in user_permissions.items():

      perm = user_items.get('permissions', {})

      if 'general' in perm.keys():
        for gp in perm.get('general', []):
          if isinstance(gp, str):
            user_permissions[user]['permissions']['general'][perm['general'].index(gp)] = permissions.PermissionAction(gp)

      for wf, wf_permissions in list(perm.get('workflows', {}).items()):

        for stage, stage_permissions in list(user_permissions[user]['permissions']['workflows'][wf].get('stages', {}).items()):

          for i, sp in enumerate(user_permissions[user]['permissions']['workflows'][wf]['stages'][stage]):
             if isinstance(sp, str):
                user_permissions[user]['permissions']['workflows'][wf]['stages'][stage][i] = permissions.PermissionAction(sp)

        if 'general' in wf_permissions.keys():
          for i, wfp in enumerate(wf_permissions.get('general', [])):
            if isinstance(wfp, str):
              user_permissions[user]['permissions']['workflows'][wf]['general'][i] = permissions.PermissionAction(wfp)

      if 'general' in perm.keys():
        for i, gp in enumerate(perm.get('general', [])):
          if isinstance(gp, str):
            user_permissions[user]['permissions']['general'][i] = permissions.PermissionAction(gp)
        
      new_permi = None

      if type == 'user':
        new_permi = permissions.User(
                      roles=user_items.get('roles', []), 
                      permissions=permissions.Permissions(
                        general=perm.get('general', []), 
                        workflows=perm.get('workflows', {})
                      ),
                      detailed_infos=permissions.DetailedInfos(
                        description=user_items.get('detailed_infos', {}).get('description', ''),
                        mail=user_items.get('detailed_infos', {}).get('mail', ''),
                        extra=user_items.get('detailed_infos', {}).get('extra', {})
                      )
        )

      if type == 'role':
        new_permi = permissions.Role(
                      permissions=permissions.Permissions(
                        general=perm.get('general', []), 
                        workflows=perm.get('workflows', {})
                      ),
                      detailed_infos=permissions.DetailedInfos(
                        description=user_items.get('detailed_infos', {}).get('description', ''),
                        mail=user_items.get('detailed_infos', {}).get('mail', ''),
                        extra=user_items.get('detailed_infos', {}).get('extra', {})
                      )
        )

      user_permissions[user] = new_permi
