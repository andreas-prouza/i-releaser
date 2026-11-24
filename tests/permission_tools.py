"""Permissions of a test without the web app: a temporary user_permissions.json"""
import json, os
from unittest.mock import patch

from etc import constants
from modules import permission_config


def use_permissions(directory: str, users: dict[str, list[str]]):
    """
    Starts a patch of C_USER_PERMISSIONS with the given users and their general permissions. Stop it with `stop_permissions`.
    """

    file = os.path.join(directory, 'user_permissions.json')
    with open(file, 'w') as f:
        json.dump({'users': {user: {'roles': [], 'permissions': {'general': general, 'workflows': {}}} for user, general in users.items()}, 'roles': {}}, f)

    p = patch.object(constants, 'C_USER_PERMISSIONS', file)
    p.start()
    permission_config.PermissionKonfig.check_reload(force=True)
    return p


def stop_permissions(p) -> None:

    p.stop()
    # The next test loads its own file
    permission_config.PermissionKonfig._PermissionKonfig__file_hash = None
