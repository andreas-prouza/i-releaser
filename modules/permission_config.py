import contextlib
import logging
import threading
import time
from typing import Dict, List

from etc import constants
from modules import current_user, errors, files, permissions





def check_user_permission(action : permissions.PermissionAction, workflow:str|None =None, stage:str|None = None, stage_id:int|None =None):

    user = current_user.get_user()

    if not is_user_allowed(user, action, workflow, stage, stage_id):
        raise errors.Permission_Denied_Error(f"User {user} does not have permission '{permissions.PermissionAction(action).value}' (workflow: {workflow}, stage: {stage or stage_id})")





def get_mail(user: str|None) -> str:
    """The e-mail address of the user in user_permissions.json ('' if it has none), e.g. for notifications"""

    if not user:
        return ''

    PermissionKonfig.check_reload()
    found = PermissionKonfig._users_by_name.get(user.lower())
    return (found.detailed_infos.mail or '').strip() if found is not None else ''



def get_users_of_role(role: str) -> list[str]:
    """The users (lower case) who have the role, without case"""

    PermissionKonfig.check_reload()
    return sorted(name for name, user in PermissionKonfig._users_by_name.items() if role.lower() in [r.lower() for r in user.roles])



def is_user_allowed(user, action : permissions.PermissionAction, workflow:str|None =None, stage:str|None =None, stage_id:int|None =None):

    if user is None:
        logging.warning("User is None")
        return False

    user = user.lower()
    if workflow is not None:
        workflow = workflow.lower()

    if stage is None and stage_id is not None:
        # Here: the data module imports the modules of the deployment, which import this one
        from modules.db import stage_data
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
        role_permission = PermissionKonfig.get_role_permissions(role)
        if is_permission_allowed(role_permission.permissions, action, workflow, stage):
            logging.debug(f"User {user} has permission {action} through role {role} (workflow: {workflow}, stage: {stage})")
            return True

    logging.info(f"User {user} does not have permission {action} (workflow: {workflow}, stage: {stage})")
    return False



def get_readable_workflows(workflows: list[str]) -> list[str]|None:
    """
    Args:
        workflows (list): Names of the workflows to check

    Returns:
        list: Those the current user may read. None if the user may read all workflows (also unknown ones).
    """

    user = current_user.get_user()

    if is_user_allowed(user, permissions.PermissionAction.READ):
        return None

    return [wf for wf in workflows if is_user_allowed(user, permissions.PermissionAction.READ, wf)]




def is_permission_allowed(current_permission: permissions.Permissions, action : permissions.PermissionAction, workflow=None, stage=None):

    if action in current_permission.general:
        return True

    if workflow is None:
        return False

    # Names of workflows and stages are compared without case: the permissions page saves them as they are
    # written in the workflow (e.g. `PROD`), docs/permissions.md writes them in lower case (docs/bugfixes/stage-permissions-case.md)
    workflows = {name.lower(): value for name, value in current_permission.workflows.items()}
    current_wf: dict|None = workflows.get(workflow.lower())

    if current_wf is None:
        return False

    # A workflow entry written by hand may have only one of them
    if permissions.PermissionAction(action) in (current_wf.get('general') or []):
        return True

    if stage is not None:
        stages = {name.lower(): value for name, value in (current_wf.get('stages') or {}).items()}
        if permissions.PermissionAction(action) in stages.get(stage.lower(), []):
            return True

    return False








class PermissionKonfig:


    __last_loaded = 0
    __reload_interval = 2
    __file_hash = None

    allowed_users = []
    role_permissions: Dict[str, permissions.Role] = {}
    user_permissions: Dict[str, permissions.User] = {}
    # The same, by the name in lower case: names are compared without case (IBM i profiles have no case)
    _users_by_name: Dict[str, permissions.User] = {}
    _roles_by_name: Dict[str, permissions.Role] = {}


    @staticmethod
    def get_user_list() -> list[str]:

        PermissionKonfig.check_reload()
        return PermissionKonfig.allowed_users



    @staticmethod
    def get_user_permissions(user) -> permissions.User:

        PermissionKonfig.check_reload()
        return PermissionKonfig._users_by_name.get(user.lower(), permissions.User())



    @staticmethod
    def get_role_permissions(role: str) -> permissions.Role:

        PermissionKonfig.check_reload()
        return PermissionKonfig._roles_by_name.get(role.lower(), permissions.Role())



    @staticmethod
    def add_user_permission(name: str, roles: List[str]|None = None, general: List[permissions.PermissionAction]|None = None, workflows: Dict[str, permissions.PermissionWorkflow]|None = None, description='', mail='', extra: dict|None=None, data: dict|None=None):

        data = data or {}
        PermissionKonfig.check_reload()

        if name.lower() in PermissionKonfig._users_by_name:
            raise errors.Conflict_Error(f"User {name} already exists")

        perm: permissions.Permissions = permissions.Permissions(general=general or data.get('general', []), workflows=workflows or data.get('workflows', {}))
        PermissionKonfig.user_permissions[name.lower()] = permissions.User(permissions=perm, roles=roles or data.get('roles', []), detailed_infos=permissions.DetailedInfos(description=description or data.get('detailed_infos', {}).get('description', ''), mail=mail or data.get('detailed_infos', {}).get('mail', ''), extra=extra or data.get('detailed_infos', {}).get('extra', {})))
        if name.lower() not in PermissionKonfig.allowed_users:
            PermissionKonfig.allowed_users.append(name.lower())

        PermissionKonfig.save_permissions()





    @staticmethod
    def add_role_permission(name: str, general: List[str]|None = None, data: dict|None = None):

        data = data or {}
        PermissionKonfig.check_reload()

        if name.lower() in PermissionKonfig._roles_by_name:
            raise errors.Conflict_Error(f"Role {name} already exists")

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
        PermissionKonfig.check_reload(force=True)




    @staticmethod
    def check_reload(force: bool=False):
        """force: read the file now, not only every few seconds (before a change)"""

        current_time = time.time()

        if force or current_time - PermissionKonfig.__last_loaded > PermissionKonfig.__reload_interval:

            file_hash = files.get_file_hash(constants.C_USER_PERMISSIONS)

            # Checked again after the interval, not with each check of a permission
            PermissionKonfig.__last_loaded = current_time

            if file_hash == PermissionKonfig.__file_hash:
                return

            try:
                data = files.getJson(constants.C_USER_PERMISSIONS, retry=True)
            except Exception as e:
                data = None
                logging.error(f"Could not load permissions from {constants.C_USER_PERMISSIONS}: {e}. The permissions loaded before stay valid.")

            if not isinstance(data, dict):
                return

            user_permissions = data.get('users', {})
            role_permissions = data.get('roles', {})

            # Convert string permissions to PermissionAction objects
            # Before they are used: requests run in parallel threads
            PermissionKonfig.convert_permissions('user', user_permissions)
            PermissionKonfig.convert_permissions('role', role_permissions)
            PermissionKonfig.user_permissions = user_permissions
            PermissionKonfig.role_permissions = role_permissions
            logging.debug(f"Reloaded user permissions: {PermissionKonfig.user_permissions}")
            logging.debug(f"Reloaded role permissions: {PermissionKonfig.role_permissions}")

            PermissionKonfig._users_by_name = {name.lower(): value for name, value in user_permissions.items()}
            PermissionKonfig._roles_by_name = {name.lower(): value for name, value in role_permissions.items()}
            PermissionKonfig.allowed_users = list(PermissionKonfig._users_by_name.keys())
            PermissionKonfig.__file_hash = file_hash



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

                for stage in list(user_permissions[user]['permissions']['workflows'][wf].get('stages', {})):

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



#-----------------------------------------------------------------------------------------------
# Permissions page (docs/features/web-ui-permissions-page.md)
#-----------------------------------------------------------------------------------------------

Action = permissions.PermissionAction

# Which permission is checked on which level (docs/permissions.md#permissions-1): the page offers only these
# In the order of the columns: the permissions which are not checked yet at the end
# `deploy` isn't offered anymore: it has never been checked (docs/features/four-eyes-check.md). Old files may still contain it, it has no effect.
ORDER = [Action.ADMIN, Action.READ, Action.START_WORKFLOW, Action.RUN_WORKFLOW, Action.CHANGE_CHECK_ERROR, Action.CANCEL_WORKFLOW,
         Action.EDIT_CUSTOM_DATA, Action.FOUR_EYES_CHECK]

LEVEL_ACTIONS = {
  'general': [a.value for a in ORDER],
  'workflow': [a.value for a in ORDER if a != Action.ADMIN],
  'stage': [Action.RUN_WORKFLOW.value, Action.CHANGE_CHECK_ERROR.value, Action.FOUR_EYES_CHECK.value],
}
NOT_CHECKED = []

MAX_NAME_LENGTH = 64

# A version check and the change it allows happen together
_CHANGE_THREAD_LOCK = threading.Lock()



@contextlib.contextmanager
def change_lock():
    """
    For a change of the permissions: check the version, change, write. Between the threads and the processes of the web app
    (gunicorn runs several), see docs/bugfixes/minor-web-defects-2026-11.md, item 5.
    """

    with _CHANGE_THREAD_LOCK, files.lock(f"{constants.C_USER_PERMISSIONS}.lock"):
        yield



def get_version() -> str:
    """Changes with every change of the file of the permissions (also an edit by hand)"""
    try:
        return files.get_file_hash(constants.C_USER_PERMISSIONS) or ''
    except OSError:
        return ''



def check_version(version: str|None) -> None:
    """
    Raises:
        errors.Conflict_Error: The permissions have been changed since the page read them
    """
    if version is not None and version != get_version():
        raise errors.Conflict_Error("The permissions have been changed meanwhile (in another session or in the file). Load the current state and try again.")



def check_name(name, existing: list[str], what: str) -> str:
    """
    A new user or role: not empty, no control characters, at most MAX_NAME_LENGTH characters, unique (without case).

    Raises:
        errors.Invalid_Input_Error
    """

    if not isinstance(name, str) or name.strip() == '':
        raise errors.Invalid_Input_Error(f"The name of the {what} is empty")
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise errors.Invalid_Input_Error(f"The name of the {what} contains control characters")
    if len(name) > MAX_NAME_LENGTH:
        raise errors.Invalid_Input_Error(f"The name of the {what} is longer than {MAX_NAME_LENGTH} characters")
    if name.strip().lower() in [e.lower() for e in existing]:
        raise errors.Conflict_Error(f"The {what} {name} exists already")

    return name.strip()



def has_admin(users: dict, roles: dict) -> bool:
    """At least one user has `admin`, own or from a role"""

    for user in users.values():
        if Action.ADMIN in user.permissions.general:
            return True
        for role in user.roles:
            role_obj = roles.get(role) or roles.get(str(role).lower())
            if role_obj is not None and Action.ADMIN in role_obj.permissions.general:
                return True
    return False



def _values(actions) -> list[str]:
    return [a.value if isinstance(a, Action) else str(a) for a in actions or []]



def _lower_keys(data: dict) -> dict:
    return {str(k).lower(): v for k, v in (data or {}).items()}



def get_effective(own: permissions.Permissions, roles: list[tuple[str, permissions.Permissions]]) -> dict:
    """
    For each row of the table of a user or role (General, its workflows and their stages, also those which only come
    from roles): the permissions it has from somewhere else, and where from.

    Returns:
        {'general': {action: [source]}, 'workflows': {workflow: {'general': {...}, 'stages': {stage: {...}}}}}
    """

    def add(target: dict, actions, source: str):
        for action in _values(actions):
            target.setdefault(action, [])
            if source not in target[action]:
                target[action].append(source)

    result = {'general': {}, 'workflows': {}}
    for role, perm in roles:
        add(result['general'], perm.general, f"role {role}")

    # Rows: own workflows and stages, and those of the roles
    rows = {}
    for workflows in [own.workflows] + [perm.workflows for _, perm in roles]:
        for wf, wf_perm in (workflows or {}).items():
            stages = rows.setdefault(wf.lower(), {'name': wf, 'stages': {}})['stages']
            for stage in (wf_perm or {}).get('stages', {}) or {}:
                stages.setdefault(stage.lower(), stage)

    for key, row in rows.items():
        wf_result = result['workflows'].setdefault(row['name'], {'general': {}, 'stages': {}})
        add(wf_result['general'], own.general, 'General')
        own_wf = _lower_keys(own.workflows).get(key) or {}

        for role, perm in roles:
            add(wf_result['general'], perm.general, f"role {role}")
            add(wf_result['general'], (_lower_keys(perm.workflows).get(key) or {}).get('general', []), f"role {role}")

        for stage_key, stage in row['stages'].items():
            stage_result = wf_result['stages'].setdefault(stage, {})
            add(stage_result, own.general, 'General')
            add(stage_result, own_wf.get('general', []), f"workflow {row['name']}")
            for role, perm in roles:
                role_wf = _lower_keys(perm.workflows).get(key) or {}
                add(stage_result, perm.general, f"role {role}")
                add(stage_result, role_wf.get('general', []), f"role {role}")
                add(stage_result, _lower_keys(role_wf.get('stages', {})).get(stage_key, []), f"role {role}")

    return result



def _as_data(perm: permissions.Permissions) -> dict:
    return {
      'general': _values(perm.general),
      'workflows': {wf: {'general': _values((wf_perm or {}).get('general', [])),
                         'stages': {stage: _values(actions) for stage, actions in ((wf_perm or {}).get('stages', {}) or {}).items()}}
                    for wf, wf_perm in (perm.workflows or {}).items()},
    }



def get_state() -> dict:
    """Everything the permissions page shows, with the version it has to send with a change"""

    PermissionKonfig.check_reload()
    users = PermissionKonfig.user_permissions
    roles = PermissionKonfig.role_permissions

    from modules import workflow
    workflows = [{'name': wf['name'], 'stages': [stage['name'] for stage in wf.get('stages', [])]} for wf in workflow.Workflow.get_all_workflows_json()]

    return {
      'version': get_version(),
      'levels': LEVEL_ACTIONS,
      'not_checked': NOT_CHECKED,
      'workflows': workflows,
      'users': {name: {
                  'roles': list(user.roles),
                  'permissions': _as_data(user.permissions),
                  'detailed_infos': {'description': user.detailed_infos.description or '', 'mail': user.detailed_infos.mail or ''},
                  'effective': get_effective(user.permissions, [(r, roles[r].permissions) for r in user.roles if r in roles]),
                } for name, user in sorted(users.items())},
      'roles': {name: {
                  'permissions': _as_data(role.permissions),
                  'users': sorted(u for u, user in users.items() if name in user.roles),
                  'effective': get_effective(role.permissions, []),
                } for name, role in sorted(roles.items())},
    }
