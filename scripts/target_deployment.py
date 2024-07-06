from __future__ import annotations
import os

from etc import constants
from modules import meta_file as mf, stages as s
from modules import deploy_action as da
from modules.cmd_status import Status as Cmd_Status


def set_cmd_restore_objects_on_target(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:
    """
     RSTLIB SAVLIB(PROUZALIB) DEV(*SAVF) SAVF(QGPL/PROUZASAVF) RSTLIB(RSTLIB)
            SELECT((*INCLUDE TEST *PGM) (*INCLUDE TEST *FILE)) 
    """

    if action.status == Cmd_Status.FINISHED or (action.status == Cmd_Status.FAILED and action.check_error == False):
        return

    actions = stage_obj.actions

    clear_files = stage_obj.clear_files
    deployment_dir = f"{stage_obj.base_dir}/{os.path.basename(os.path.dirname(meta_file.file_name))}"
    last_added_action = action

    for lib in meta_file.deploy_objects.get_lib_list_with_prod_lib():

      # Delete old savf
      cmd = f"DLTF FILE({meta_file.main_deploy_lib}/{lib['lib']})"
      last_added_action = actions.add_action_cmd(cmd=cmd, environment=da.Command_Type.QSYS, processing_step=action.processing_step, stage=stage_obj.name, add_after=last_added_action)

      # Copy savf from IFS to QSYS file system
      savf = f"{meta_file.main_deploy_lib}/{lib['lib']}"
      savf_ifs_qsys = f"/qsys.lib/{meta_file.main_deploy_lib}.lib/{lib['lib']}.file"
      savf_ifs = f"{deployment_dir}/{lib['lib']}.file"

      cmd = f"CPYFRMSTMF FROMSTMF('{savf_ifs}') TOSTMF('{savf_ifs_qsys}') STMFOPT(*REPLACE)"
      last_added_action = actions.add_action_cmd(cmd=cmd, environment=da.Command_Type.QSYS, processing_step=action.processing_step, stage=stage_obj.name, add_after=last_added_action)

      # Restore all objects
      restore_to_lib = lib['prod_lib']
      if stage_obj.lib_replacement_necessary:
        if lib['prod_lib'] in stage_obj.lib_mapping.keys():
          restore_to_lib = stage_obj.lib_mapping[lib['lib']]

      includes = ''
      
      for obj in meta_file.deploy_objects.get_obj_list_by_lib(lib['lib']):
        includes += f" (*INCLUDE {obj.name} {obj.type})"

      last_added_action = actions.add_action_cmd(f"RSTLIB SAVLIB({lib['lib']}) DEV(*SAVF) SAVF({meta_file.main_deploy_lib}/{lib['lib']}) SELECT({includes}) RSTLIB({restore_to_lib})", 
            environment=da.Command_Type.QSYS, processing_step=action.processing_step, stage=stage_obj.name, add_after=last_added_action)

    stage_obj.set_status('prepare')
    meta_file.write_meta_file()
