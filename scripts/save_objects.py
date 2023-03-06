from __future__ import annotations
import os

from etc import constants
from modules import meta_file as mf
from modules import deploy_action as da


def set_init_cmds_for_save(meta_file: mf.Meta_File, stage: str) -> None:
    """Create library & save files to transfer new objects

    Args:
        meta_file (str): filename + path of meta-file
        stage (str): Run for this stage
    """

    # meta_file = mf.Meta_File.load_json_file(meta_file_name)

    actions = meta_file.actions

    actions.add_action_cmd(
        f"CRTLIB {meta_file.main_deploy_lib}",
        environment=da.Command_Type.QSYS,
        processing_step=da.Processing_Step.SAVE,
        stage=stage,
        check_error=False,
    )

    # Create save files for each lib to deploy
    for lib in meta_file.deploy_objects.get_lib_list_with_prod_lib():
        actions.add_action_cmd(
            f"CRTSAVF {meta_file.main_deploy_lib}/{lib['lib']}",
            environment=da.Command_Type.QSYS,
            processing_step=da.Processing_Step.SAVE,
            stage=stage,
            check_error=False,
        )
        actions.add_action_cmd(
            f"CLRSAVF {meta_file.main_deploy_lib}/{lib['lib']}",
            environment=da.Command_Type.QSYS,
            processing_step=da.Processing_Step.SAVE,
            stage=stage,
        )

    meta_file.current_stages.get_stage(stage).set_status("prepare")
    meta_file.write_meta_file()


def set_cmd_object_to_savf(meta_file: mf.Meta_File, stage: str) -> None:
    """
    SAVLIB LIB(PROUZALIB) DEV(*SAVF) SAVF(QGPL/PROUZASAVF)
           SELECT(
                  (*INCLUDE TEST *PGM)
                  (*INCLUDE TEST *FILE)
                 )
    """
    actions = meta_file.actions
    clear_files = meta_file.current_stages.get_stage(stage).clear_files
    deployment_dir = os.path.dirname(os.path.realpath(meta_file.file_name))

    for lib in meta_file.deploy_objects.get_lib_list_with_prod_lib():
        includes = ""
        for obj in meta_file.deploy_objects.get_obj_list_by_lib(lib["lib"]):
            includes += f" (*INCLUDE {obj.name} {obj.type})"

            if (
                clear_files is True
                and obj.attribute in constants.C_PHYSICAL_FILE_ATTRIBUTES
            ):
                actions.add_action_cmd(
                    f"CLRPFM {obj.lib}/{obj.name}",
                    environment=da.Command_Type.QSYS,
                    processing_step=da.Processing_Step.SAVE,
                    stage=stage,
                )

        savf = f"{meta_file.main_deploy_lib}/{lib['lib']}"
        savf_ifs_qsys = (
            f"/qsys.lib/{meta_file.main_deploy_lib}.lib/{lib['lib']}.file"
        )
        savf_ifs_target = f"{deployment_dir}/{lib['lib']}.file"

        actions.add_action_cmd(
            f"SAVLIB LIB({lib['lib']}) DEV(*SAVF) SAVF({savf}) \
            SELECT({includes}) DTACPR(*HIGH)",
            environment=da.Command_Type.QSYS,
            processing_step=da.Processing_Step.SAVE,
            stage=stage,
        )

        cmd = f"CPYTOSTMF FROMMBR('{savf_ifs_qsys}') TOSTMF('{savf_ifs_target}') STMFOPT(*REPLACE)"
        actions.add_action_cmd(
            cmd=cmd,
            environment=da.Command_Type.QSYS,
            processing_step=da.Processing_Step.SAVE,
            stage=stage,
        )

    meta_file.current_stages.get_stage(stage).set_status("prepare")
    meta_file.write_meta_file()
