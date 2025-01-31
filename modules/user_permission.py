from __future__ import annotations
import logging

from etc import user_cfg
from webapp.etc import db_config, global_cfg, web_constants
from modules import permission



def is_user_allowed(user, action : permission.Permission, workflow=None, stage=None):

    user_permission = user_cfg.USER_PERMISSION

    logging.debug(f"{user=}; {action=}: {type(action)}")

    if user not in user_permission.keys():
        logging.info(f"{user=} is not in list: {user_permission.keys()}")
        return False

    current_permission = user_permission[user]

    if 'general' in current_permission.keys() and action in current_permission['general']:
        return True

    if workflow is not None and 'workflows' in current_permission.keys() and workflow in current_permission['workflows'].keys():
        current_wf = current_permission['workflows'][workflow]

        if 'general' in current_wf.keys() and current_wf['general'] == action:
            return True

        if stage is not None and 'stages' in current_wf.keys() and stage in current_wf['stages'].keys():
            current_stage = current_wf['stages'][stage]

            if action in current_stage:
                return True


    logging.info(f"No permission for {user=}, {action=}, {workflow=}, {stage=}")

    return False
