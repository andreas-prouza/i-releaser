from __future__ import annotations
import os

from etc import constants
from modules import meta_file as mf, stages as s
from modules import deploy_action as da
from modules.cmd_status import Status as Cmd_Status


def set_init_cmds_for_deployment(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:
    """Prepare deployment on target system

      * Create deployment library
      * Create backup library
      * Create SAVF for each library which will be deployed to save old objects

    Args:
        stage (str): Run for this stage
    """

    if action.status == Cmd_Status.FINISHED or (action.status == Cmd_Status.FAILED and action.check_error == False):
        return

    actions = stage_obj.actions
    last_added_action = action

    last_added_action = actions.add_action_cmd(
        f"CRTLIB {meta_file.backup_deploy_lib}",
        environment=da.Command_Type.QSYS,
        processing_step=action.processing_step,
        stage=stage_obj.name,
        check_error=False,
        add_after=last_added_action
    )

    last_added_action = actions.add_action_cmd(
        f"CRTLIB {meta_file.main_deploy_lib}",
        environment=da.Command_Type.QSYS,
        processing_step=action.processing_step,
        stage=stage_obj.name,
        check_error=False,
        add_after=last_added_action
    )

    # Create save files for each lib to deploy
    for lib in meta_file.deploy_objects.get_lib_list_from_prod():

        last_added_action = actions.add_action_cmd(
            f"CRTSAVF {meta_file.backup_deploy_lib}/{lib}",
            environment=da.Command_Type.QSYS,
            processing_step=action.processing_step,
            stage=stage_obj.name,
            check_error=False,
            add_after=last_added_action
        )

        last_added_action = actions.add_action_cmd(
            f"CLRSAVF {meta_file.backup_deploy_lib}/{lib}",
            environment=da.Command_Type.QSYS,
            processing_step=action.processing_step,
            stage=stage_obj.name,
            add_after=last_added_action
        )


