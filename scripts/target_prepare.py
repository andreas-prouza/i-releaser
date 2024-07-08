from __future__ import annotations
import os

from etc import constants
from modules import meta_file as mf, stages as s
from modules import deploy_action as da
from modules import ibm_i_commands
from modules.cmd_status import Status as Cmd_Status
from modules.object_status import Status as Obj_Status


def init_deployment(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:
    """Prepare deployment on target system

      * Create deployment library
      * Create backup library
      * Create SAVF for each library which will be deployed to save old objects

    Args:
        stage (str): Run for this stage
    """

    actions = stage_obj.actions
    last_added_action = action
    cmd = ibm_i_commands.IBM_i_commands(meta_file)

    last_added_action = action.sub_actions.add_action(da.Deploy_Action(
        cmd=f"CRTLIB {meta_file.backup_deploy_lib}",
        environment=da.Command_Type.QSYS,
        processing_step=action.processing_step,
        stage=stage_obj.name,
        check_error=False
    ))
    cmd.execute_action(stage=stage_obj, action=last_added_action)

    last_added_action = action.sub_actions.add_action(da.Deploy_Action(
        cmd=f"CRTLIB {meta_file.main_deploy_lib}",
        environment=da.Command_Type.QSYS,
        processing_step=action.processing_step,
        stage=stage_obj.name,
        check_error=False
    ))
    cmd.execute_action(stage=stage_obj, action=last_added_action)

    # Create save files for each lib to deploy
    for lib in meta_file.deploy_objects.get_lib_list_from_prod():

        last_added_action = action.sub_actions.add_action(da.Deploy_Action(
            cmd=f"CRTSAVF {meta_file.backup_deploy_lib}/{lib}",
            environment=da.Command_Type.QSYS,
            processing_step=action.processing_step,
            stage=stage_obj.name,
            check_error=False
        ))
        cmd.execute_action(stage=stage_obj, action=last_added_action)

        last_added_action = action.sub_actions.add_action(da.Deploy_Action(
            cmd=f"CLRSAVF {meta_file.backup_deploy_lib}/{lib}",
            environment=da.Command_Type.QSYS,
            processing_step=action.processing_step,
            stage=stage_obj.name,
            check_error=action.check_error
        ))
        cmd.execute_action(stage=stage_obj, action=last_added_action)


