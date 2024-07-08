from __future__ import annotations
import os, logging

from etc import constants
from modules import meta_file as mf, stages as s
from modules.cmd_status import Status as Cmd_Status
from modules.object_status import Status as Obj_Status
from modules import deploy_action as da
from modules import ibm_i_commands


def init_save(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:
    """Create library & save files to transfer new objects

    Args:
        meta_file (str): filename + path of meta-file
        stage_obj (Stage): Run for this stage
    """

    actions = stage_obj.actions
    cmd = ibm_i_commands.IBM_i_commands(meta_file)
    meta_file.deploy_objects.set_objects_status(Obj_Status.IN_SAVE)

    last_added_action = action.sub_actions.add_action(da.Deploy_Action(
        cmd=f"CRTLIB {meta_file.main_deploy_lib}",
        environment=da.Command_Type.QSYS,
        processing_step=action.processing_step,
        stage=stage_obj.name,
        check_error=False
    ))
    cmd.execute_action(stage=stage_obj, action=last_added_action)

    # Create save files for each lib to deploy
    for lib in meta_file.deploy_objects.get_lib_list_with_prod_lib():

        last_added_action = action.sub_actions.add_action(da.Deploy_Action(
            cmd=f"CRTSAVF {meta_file.main_deploy_lib}/{lib['lib']}",
            environment=da.Command_Type.QSYS,
            processing_step=action.processing_step,
            stage=stage_obj.name,
            check_error=False
        ))
        cmd.execute_action(stage=stage_obj, action=last_added_action)

        last_added_action = action.sub_actions.add_action(da.Deploy_Action(
            cmd=f"CLRSAVF {meta_file.main_deploy_lib}/{lib['lib']}",
            environment=da.Command_Type.QSYS,
            processing_step=action.processing_step,
            stage=stage_obj.name,
            check_error=action.check_error
        ))
        cmd.execute_action(stage=stage_obj, action=last_added_action)




def save_objects_to_savf(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:
    """
    SAVLIB LIB(PROUZALIB) DEV(*SAVF) SAVF(QGPL/PROUZASAVF)
           SELECT(
                  (*INCLUDE TEST *PGM)
                  (*INCLUDE TEST *FILE)
                 )
    """
    
    actions = stage_obj.actions
    cmd = ibm_i_commands.IBM_i_commands(meta_file)

    clear_files = stage_obj.clear_files
    deployment_dir = os.path.dirname(os.path.realpath(meta_file.file_name))
    last_added_action = action

    for lib in meta_file.deploy_objects.get_lib_list_with_prod_lib():
        includes = ""
        for obj in meta_file.deploy_objects.get_obj_list_by_prod_lib(lib["prod_lib"]):
            includes += f" (*INCLUDE {obj.name} *{obj.type})"

            if (
                clear_files is True
                and obj.attribute in constants.C_PHYSICAL_FILE_ATTRIBUTES
            ):
                last_added_action = action.sub_actions.add_action(da.Deploy_Action(
                    cmd=f"CLRPFM {obj.lib}/{obj.name}",
                    environment=da.Command_Type.QSYS,
                    processing_step=action.processing_step,
                    stage=stage_obj.name,
                    check_error=action.check_error
                ))
                cmd.execute_action(stage=stage_obj, action=last_added_action)

        savf = f"{meta_file.main_deploy_lib}/{lib['lib']}"
        savf_ifs_qsys = (
            f"/qsys.lib/{meta_file.main_deploy_lib}.lib/{lib['lib']}.file"
        )
        savf_ifs_target = f"{deployment_dir}/{lib['lib']}.file"

        last_added_action = action.sub_actions.add_action(da.Deploy_Action(
            cmd=f"SAVLIB LIB({lib['lib']}) DEV(*SAVF) SAVF({savf}) CLEAR(*ALL) SELECT({includes}) DTACPR(*HIGH)",
            environment=da.Command_Type.QSYS,
            processing_step=action.processing_step,
            stage=stage_obj.name,
            check_error=action.check_error
        ))
        cmd.execute_action(stage=stage_obj, action=last_added_action)

        last_added_action = action.sub_actions.add_action(da.Deploy_Action(
            cmd=f"CPYTOSTMF FROMMBR('{savf_ifs_qsys}') TOSTMF('{savf_ifs_target}') STMFOPT(*REPLACE)",
            environment=da.Command_Type.QSYS,
            processing_step=action.processing_step,
            stage=stage_obj.name,
            check_error=action.check_error,
            run_in_new_job=True
        ))
        cmd.execute_action(stage=stage_obj, action=last_added_action)

    meta_file.deploy_objects.set_objects_status(Obj_Status.SAVED)
    logging.debug(f"Number of actions generated: {len(stage_obj.actions)}")

