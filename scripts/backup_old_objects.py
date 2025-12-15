from __future__ import annotations
import os

from etc import constants
from modules import meta_file as mf, stages as s
from modules import deploy_action as da
from modules import ibm_i_commands

from modules.cmd_status import Status as Cmd_Status
from modules.object_status import Status as Obj_Status


def backup_objects_on_target(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:
    """
     Save production objects bevore deployment
    """

    actions = stage_obj.actions
    cmd = ibm_i_commands.IBM_i_commands(meta_file)

    includes = ''
    clear_files = stage_obj.clear_files

    last_action = action
    meta_file.deploy_objects.set_objects_status(Obj_Status.IN_BACKUP)

    for lib in meta_file.deploy_objects.get_lib_list_from_prod():

        for obj in meta_file.deploy_objects.get_obj_list_by_prod_lib(lib):
            obj_name = obj.name.replace('$', '\\$')
            includes += f" (*INCLUDE {obj_name} *{obj.type})"

        last_action = action.sub_actions.add_action(da.Deploy_Action(
            cmd=f"SAVLIB LIB({lib}) DEV(*SAVF) SAVF({meta_file.backup_deploy_lib}/{lib}) CLEAR(*ALL) SELECT({includes}) DTACPR(*HIGH)", 
            environment=da.Command_Type.QSYS, 
            processing_step=action.processing_step, 
            stage=stage_obj.name,
            check_error=action.check_error
        ))
        cmd.execute_action(stage=stage_obj, action=last_action)

    meta_file.deploy_objects.set_objects_status(Obj_Status.BACKUPED)
    meta_file.write_meta_file()
