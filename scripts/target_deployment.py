from __future__ import annotations
import os

from etc import constants
from modules import meta_file as mf
from modules import deploy_action as da


def set_cmd_restore_objects_on_target(meta_file: mf.Meta_File, stage: str, processing_step: str) -> None:
    """
     RSTLIB SAVLIB(PROUZALIB) DEV(*SAVF) SAVF(QGPL/PROUZASAVF) RSTLIB(RSTLIB)
            SELECT((*INCLUDE TEST *PGM) (*INCLUDE TEST *FILE)) 
    """
    actions = meta_file.actions
    clear_files = meta_file.stages.get_stage(stage).clear_files
    current_stage = meta_file.stages.get_stage(stage)
    deployment_dir = f"{current_stage.base_dir}/{os.path.basename(os.path.dirname(meta_file.file_name))}"

    for lib in meta_file.deploy_objects.get_lib_list_with_prod_lib():

      # Delete old savf
      cmd = f"DLTF FILE({meta_file.main_deploy_lib}/{lib['lib']})"
      actions.add_action_cmd(cmd=cmd, environment=da.Command_Type.QSYS, processing_step=processing_step, stage=stage)

      # Copy savf from IFS to QSYS file system
      savf = f"{meta_file.main_deploy_lib}/{lib['lib']}"
      savf_ifs_qsys = f"/qsys.lib/{meta_file.main_deploy_lib}.lib/{lib['lib']}.file"
      savf_ifs = f"{deployment_dir}/{lib['lib']}.file"

      cmd = f"CPYFRMSTMF FROMSTMF('{savf_ifs}') TOSTMF('{savf_ifs_qsys}') STMFOPT(*REPLACE)"
      actions.add_action_cmd(cmd=cmd, environment=da.Command_Type.QSYS, processing_step=processing_step, stage=stage)

      # Restore all objects
      restore_to_lib = lib['prod_lib']
      if current_stage.lib_replacement_necessary:
        if lib['prod_lib'] in current_stage.lib_mapping.keys():
          restore_to_lib = current_stage.lib_mapping[lib['lib']]

      includes = ''
      
      for obj in meta_file.deploy_objects.get_obj_list_by_lib(lib['lib']):
        includes += f" (*INCLUDE {obj.name} {obj.type})"

      actions.add_action_cmd(f"RSTLIB SAVLIB({lib['lib']}) DEV(*SAVF) SAVF({meta_file.main_deploy_lib}/{lib['lib']}) \
            SELECT({includes}) RSTLIB({restore_to_lib})", 
            environment=da.Command_Type.QSYS, processing_step=processing_step, stage=stage)

    meta_file.stages.get_stage(stage).set_status('prepare')
    meta_file.write_meta_file()
