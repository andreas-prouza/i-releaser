from __future__ import annotations
import os

from etc import constants
from modules import meta_file as mf
from modules import deploy_action as da


def set_init_cmds_for_deployment(meta_file: mf.Meta_File, stage: str, processing_step: str) -> None:
    """Prepare deployment on target system

      * Create deployment library
      * Create backup library
      * Create SAVF for each library which will be deployed to save old objects

    Args:
        stage (str): Run for this stage
    """

    actions = meta_file.actions

    actions.add_action_cmd(
        f"CRTLIB {meta_file.backup_deploy_lib}",
        environment=da.Command_Type.QSYS,
        processing_step=processing_step,
        stage=stage,
        check_error=False,
    )

    actions.add_action_cmd(
        f"CRTLIB {meta_file.main_deploy_lib}",
        environment=da.Command_Type.QSYS,
        processing_step=processing_step,
        stage=stage,
        check_error=False,
    )

    # Create save files for each lib to deploy
    for lib in meta_file.deploy_objects.get_lib_list_from_prod():
        actions.add_action_cmd(
            f"CRTSAVF {meta_file.backup_deploy_lib}/{lib}",
            environment=da.Command_Type.QSYS,
            processing_step=processing_step,
            stage=stage,
            check_error=False,
        )
        actions.add_action_cmd(
            f"CLRSAVF {meta_file.backup_deploy_lib}/{lib}",
            environment=da.Command_Type.QSYS,
            processing_step=processing_step,
            stage=stage,
        )


