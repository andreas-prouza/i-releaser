import logging
import time
from typing import List

from etc import constants, constants
from modules import files, permission, meta_file
import json




def _check_user_permission(user, action : permission.Permission, workflow=None, stage=None):
  if not is_user_allowed(user, action, workflow, stage):
    error = Exception(f"User {user} does not have permission {action} (workflow: {workflow}, stage: {stage})")
    logging.exception(error, stack_info=True)
    raise error




def is_user_allowed(user, action : permission.Permission, workflow=None, stage=None):
  
  if user is None:
    logging.warning("User is None")
    return False
  
  user = user.lower()
  if workflow is not None:
    workflow = workflow.lower()
  if stage is not None:
    stage = stage.lower()

  logging.debug(f"Check if user {user} has permission {action} (workflow: {workflow}, stage: {stage})")

  logging.debug(f"{user=}; {action=}: {type(action)}")

  if user not in UserPermission.get_user_list():
    logging.info(f"{user=} is not in list: {UserPermission.get_user_list()}")
    return False

  current_permission = UserPermission.get_user_permissions(user)

  if 'general' in current_permission.keys() and action in current_permission['general']:
    logging.debug("allowed")
    return True

  if workflow is not None and 'workflows' in current_permission.keys() and workflow in current_permission['workflows'].keys():
    current_wf = current_permission['workflows'][workflow]

    if 'general' in current_wf.keys() and action in current_wf['general']:
      logging.debug("allowed")
      return True

    if stage is not None and 'stages' in current_wf.keys() and stage in current_wf['stages'].keys():
      current_stage = current_wf['stages'][stage]

      if action in current_stage:
        logging.debug("allowed")
        return True


  logging.info(f"No permission for {user=}, {action=}, {workflow=}, {stage=}")

  return False



def get_list_of_dependent_permissions(permissions : List[permission.Permission]) -> List[permission.Permission]:

  result = permissions
  
  for p in permissions:
     if p in list(permission.PERMISSION_DEPENDENCIES.keys()):
      result.extend(get_list_of_dependent_permissions(permission.PERMISSION_DEPENDENCIES[p]))
  
  return result



def check_user_permission(action: permission.Permission, workflow=None, stage=None):
    
    def decorator(func):
        
        def wrapper(*args, **kwargs):
            
            user = meta_file.Meta_File.CURRENT_USER
            logging.debug(f"Check permission for user {user} and action {action} (workflow: {workflow}, stage: {stage})")
            logging.debug(f"{func.__name__=}, {args=}, {kwargs=}")

            _check_user_permission(user, action, workflow, stage)

            return func(*args, **kwargs)
        
        return wrapper
    
    return decorator





class UserPermission:


  __last_loaded = 0
  __reload_interval = 60
  __file_hash = None
  
  allowed_users = []
  user_permissions = {}


  @staticmethod
  def get_user_list() -> list[str]:

    UserPermission.check_reload()
    return UserPermission.allowed_users
  


  @staticmethod
  def get_user_permissions(user=None) -> dict:

    UserPermission.check_reload()
    if user is None:
        return {}
    return UserPermission.user_permissions.get(user.lower(), {})
  


  @staticmethod
  def check_reload():
    
    current_time = time.time()

    if current_time - UserPermission.__last_loaded > UserPermission.__reload_interval:

      file_hash = files.get_file_hash(constants.C_USER_PERMISSIONS)

      if file_hash == UserPermission.__file_hash:
        return

      data = files.getJson(constants.C_USER_PERMISSIONS, retry=True)
  
      UserPermission.user_permissions = data
      UserPermission.convert_permissions()
      UserPermission.allowed_users = list(UserPermission.user_permissions.keys())
      UserPermission.__file_hash = file_hash

      UserPermission.__last_loaded = current_time



  @staticmethod
  def convert_permissions() -> None:

    for user, permissions in UserPermission.user_permissions.items():

      for gp in permissions.get('general', []):
        if isinstance(gp, str):
          UserPermission.user_permissions[user]['general'][permissions['general'].index(gp)] = permission.Permission(gp)
      UserPermission.user_permissions[user]['general'] = get_list_of_dependent_permissions(UserPermission.user_permissions[user]['general'])

      for wf, wf_permissions in list(permissions.get('workflows', {}).items()):

        for stage, stage_permissions in list(UserPermission.user_permissions[user]['workflows'][wf].get('stages', {}).items()):

          for i, sp in enumerate(UserPermission.user_permissions[user]['workflows'][wf]['stages'][stage]):
             if isinstance(sp, str):
                UserPermission.user_permissions[user]['workflows'][wf]['stages'][stage][i] = permission.Permission(sp)
          UserPermission.user_permissions[user]['workflows'][wf]['stages'][stage] = get_list_of_dependent_permissions(UserPermission.user_permissions[user]['workflows'][wf]['stages'][stage])

        for i, wfp in enumerate(wf_permissions.get('general', [])):
          if isinstance(wfp, str):
            UserPermission.user_permissions[user]['workflows'][wf]['general'][i] = permission.Permission(wfp)

        UserPermission.user_permissions[user]['workflows'][wf]['general'] = get_list_of_dependent_permissions(UserPermission.user_permissions[user]['workflows'][wf]['general'])

      for i, gp in enumerate(permissions.get('general', [])):
        if isinstance(gp, str):
          UserPermission.user_permissions[user]['general'][i] = permission.Permission(gp)

      UserPermission.user_permissions[user]['general'] = get_list_of_dependent_permissions(UserPermission.user_permissions[user]['general'])