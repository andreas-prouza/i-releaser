from __future__ import annotations
import os

from etc import constants
from modules import meta_file as mf, stages as s
from modules import deploy_action as da
from modules.cmd_status import Status as Cmd_Status
from modules.object_status import Status as Obj_Status
from modules import ibm_i_commands


def restore_objects_on_target(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:
    """
     RSTLIB SAVLIB(PROUZALIB) DEV(*SAVF) SAVF(QGPL/PROUZASAVF) RSTLIB(RSTLIB)
            SELECT((*INCLUDE TEST *PGM) (*INCLUDE TEST *FILE)) 
    """


    actions = stage_obj.actions

    clear_files = stage_obj.clear_files
    deployment_dir = os.path.dirname(os.path.realpath(meta_file.file_name))
    last_added_action = action
    cmd = ibm_i_commands.IBM_i_commands(meta_file)

    meta_file.deploy_objects.set_objects_status(Obj_Status.IN_RESTORE)

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

      # Copy savf from IFS to QSYS file system
      savf = f"{meta_file.main_deploy_lib}/{lib['lib']}"
      savf_ifs_qsys = f"/qsys.lib/{meta_file.main_deploy_lib}.lib/{lib['lib']}.file"
      savf_ifs = f"{deployment_dir}/{lib['lib']}.file"

      last_added_action = action.sub_actions.add_action(da.Deploy_Action(
        cmd=f"CPYFRMSTMF FROMSTMF('{savf_ifs}') TOMBR('{savf_ifs_qsys}') MBROPT(*REPLACE)", 
        environment=da.Command_Type.QSYS, 
        processing_step=action.processing_step, 
        stage=stage_obj.name, 
        run_in_new_job=True,
        check_error=action.check_error
      ))
      cmd.execute_action(stage=stage_obj, action=last_added_action)

      # Restore all objects
      restore_to_lib = lib['prod_lib']
      if stage_obj.lib_replacement_necessary:
        if lib['prod_lib'] in stage_obj.lib_mapping.keys():
          restore_to_lib = stage_obj.lib_mapping[lib['lib']]

      includes = ''
      
      for obj in meta_file.deploy_objects.get_obj_list_by_lib(lib['lib']):
        includes += f" (*INCLUDE {obj.name} {obj.type})"

      last_added_action = action.sub_actions.add_action(da.Deploy_Action(
        cmd=f"RSTLIB SAVLIB({lib['lib']}) DEV(*SAVF) SAVF({meta_file.main_deploy_lib}/{lib['lib']}) SELECT({includes}) RSTLIB({restore_to_lib})", 
        environment=da.Command_Type.QSYS, 
        processing_step=action.processing_step, 
        stage=stage_obj.name, 
        check_error=action.check_error
      ))
      cmd.execute_action(stage=stage_obj, action=last_added_action)

    meta_file.deploy_objects.set_objects_status(Obj_Status.RESTORED)
    meta_file.write_meta_file()
