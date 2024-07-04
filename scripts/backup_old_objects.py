from __future__ import annotations
import os

from etc import constants
from modules import meta_file as mf, stages as s
from modules import deploy_action as da

from modules.cmd_status import Status as Cmd_Status


def set_cmd_backup_objects_on_target(meta_file: mf.Meta_File, stage_obj: s.Stage, processing_step: str) -> None:
    """
     Save production objects bevore deployment
    """
    actions = stage_obj.actions

    includes = ''
    clear_files = stage_obj.clear_files

    for lib in meta_file.deploy_objects.get_lib_list_from_prod():

        for obj in meta_file.deploy_objects.get_obj_list_by_prod_lib(lib):
            includes += f" (*INCLUDE {obj.name} *{obj.type})"

        actions.add_action_cmd(f"SAVLIB LIB({lib}) DEV(*SAVF) SAVF({meta_file.backup_deploy_lib}/{lib}) \
            SELECT({includes}) DTACPR(*HIGH)", 
            environment=da.Command_Type.QSYS, processing_step=processing_step, stage=stage_obj.name)

    stage_obj.set_status(Cmd_Status.PREPARE)
    meta_file.write_meta_file()
