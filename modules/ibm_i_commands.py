from __future__ import annotations
import os
import subprocess
import logging

from etc import logger_config, constants
from modules import meta_file, deploy_action as da



class IBM_i_commands:

  def __init__(self, meta_file: meta_file.Meta_File):
    self.meta_file = meta_file



  def set_init_cmds(self) -> None:
    
    actions = self.meta_file.actions

    actions.add_action_cmd(f"CRTLIB {self.meta_file.main_deploy_lib}", type=da.Command_Type.QSYS, processing_area=da.Processing_Area.SAVE)

    # Create save files for each lib to deploy
    for savf_obj in self.meta_file.object_libs:
      actions.add_action_cmd(f"CRTSAVF {self.meta_file.main_deploy_lib}/{savf_obj['savf']}", type=da.Command_Type.QSYS, processing_area=da.Processing_Area.SAVE)
      actions.add_action_cmd(f"CLRSAVF {self.meta_file.main_deploy_lib}/{savf_obj['savf']}", type=da.Command_Type.QSYS, processing_area=da.Processing_Area.SAVE)

    # Create save file for the meta file
    actions.add_action_cmd(f"CRTSAVF {self.meta_file.main_deploy_lib}/metafile", type=da.Command_Type.QSYS, processing_area=da.Processing_Area.SAVE)
    actions.add_action_cmd(f"CLRSAVF {self.meta_file.main_deploy_lib}/metafile", type=da.Command_Type.QSYS, processing_area=da.Processing_Area.SAVE)
    actions.add_action_cmd(f"SAV DEV('/qsys.lib/{self.meta_file.main_deploy_lib}.lib/metafile.file') OBJ(('{os.path.abspath(self.meta_file.file_name)}'))", type=da.Command_Type.QSYS, processing_area=da.Processing_Area.SAVE)

    for lib in self.meta_file.deploy_objects.get_lib_list():
      actions.add_action_cmd(f"CRTSAVF {self.meta_file.main_deploy_lib}/{lib}", type=da.Command_Type.QSYS, processing_area=da.Processing_Area.SAVE)

    self.meta_file.write_meta_file()



  def set_save_objects_cmd(self) -> None:
    """
     SAVLIB LIB(PROUZALIB) DEV(*SAVF) SAVF(QGPL/PROUZASAVF) 
            SELECT(
                   (*INCLUDE TEST *PGM) 
                   (*INCLUDE TEST *FILE)
                  ) 
    """
    actions = self.meta_file.actions
    includes = ''

    for lib in self.meta_file.deploy_objects.get_lib_list():

      for obj in self.meta_file.deploy_objects.get_obj_list_by_lib(lib):

        includes += f" (*INCLUDE {obj.name} {obj.type})"

      actions.add_action_cmd(f"SAVLIB LIB({lib}) DEV(*SAVF) SAVF({self.meta_file.main_deploy_lib}/{lib}) \
            SELECT({includes}) DTACPR(*HIGH)", type=da.Command_Type.QSYS, processing_area=da.Processing_Area.SAVE)

    self.meta_file.write_meta_file()



  def set_prepear_cmd_for_target(self) -> None:

    self.meta_file.actions.add_action_cmd(f"CRTLIB {self.meta_file.backup_deploy_lib}", type=da.Command_Type.QSYS, processing_area=da.Processing_Area.TARGET_PREPARE)
    self.meta_file.actions.add_action_cmd(f"mkdir -p '{constants.C_DEPLOYMENT_ROOT_DIR}'", type=da.Command_Type.PASE, processing_area=da.Processing_Area.TARGET_PREPARE)
    
    self.meta_file.write_meta_file()



  def run_commands(self, processing_area: str) -> None:
    
    for action in self.meta_file.actions.get_actions(processing_area=processing_area):

      cmd = action.cmd

      if action.type == da.Command_Type.QSYS:
        cmd = f'(cl -v "{cmd}"; cl -v "dspjoblog")'

      print(f"run {cmd}")
      
      s=subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, check=False, executable='/bin/bash')
      stdout = s.stdout
      stderr = s.stderr

      if constants.C_CONVERT_OUTPUT:
        stdout = stdout.decode(constants.C_CONVERT_FROM)
        stderr = stderr.decode(constants.C_CONVERT_FROM)

      action.stdout = stdout
      action.stderr = stderr

      if s.returncode != 0:
        print(stderr)
        action.status = 'failed'
        break

      action.status = 'finished'
    
    self.meta_file.write_meta_file()

    #iconv -f IBM-1252 -t utf-8 './logs/prouzalib/date.sqlrpgle.srvpgm.error.log' > './logs/prouzalib/date.sqlrpgle.srvpgm.error.log'_tmp && mv './logs/prouzalib/date.sqlrpgle.srvpgm.error.log'_tmp './logs/prouzalib/date.sqlrpgle.srvpgm.error.log' 
