from __future__ import annotations
import os
import subprocess
import logging
import json

from etc import logger_config, constants
from modules import meta_file
from modules import deploy_action as da
from modules import run_history as rh
from modules import stages as s



class IBM_i_commands:

  def __init__(self, meta_file: meta_file.Meta_File):
    self.meta_file = meta_file



  def set_init_cmds_for_save(self, stage: str) -> None:
    """Create library & save files to transfer new objects

    Args:
        stage (str): Run for this stage
    """
    
    actions = self.meta_file.actions

    actions.add_action_cmd(f"CRTLIB {self.meta_file.main_deploy_lib}", environment=da.Command_Type.QSYS, 
        processing_step=da.Processing_Step.SAVE, stage=stage, check_error=False)

    # Create save files for each lib to deploy
    for lib in self.meta_file.deploy_objects.get_lib_list_with_prod_lib():
      actions.add_action_cmd(f"CRTSAVF {self.meta_file.main_deploy_lib}/{lib['lib']}", 
          environment=da.Command_Type.QSYS, processing_step=da.Processing_Step.SAVE, stage=stage, check_error=False)
      actions.add_action_cmd(f"CLRSAVF {self.meta_file.main_deploy_lib}/{lib['lib']}", 
        environment=da.Command_Type.QSYS, processing_step=da.Processing_Step.SAVE, stage=stage)

    self.meta_file.current_stages.get_stage(stage).set_status('prepare')
    self.meta_file.write_meta_file()



  def set_cmd_object_to_savf(self, stage: str) -> None:
    """
     SAVLIB LIB(PROUZALIB) DEV(*SAVF) SAVF(QGPL/PROUZASAVF) 
            SELECT(
                   (*INCLUDE TEST *PGM) 
                   (*INCLUDE TEST *FILE)
                  ) 
    """
    actions = self.meta_file.actions
    clear_files = self.meta_file.current_stages.get_stage(stage).clear_files
    deployment_dir = os.path.dirname(os.path.realpath(self.meta_file.file_name))

    for lib in self.meta_file.deploy_objects.get_lib_list_with_prod_lib():

      includes = ''
      for obj in self.meta_file.deploy_objects.get_obj_list_by_lib(lib['lib']):

        includes += f" (*INCLUDE {obj.name} {obj.type})"

        if clear_files is True and obj.attribute in constants.C_PHYSICAL_FILE_ATTRIBUTES:
          actions.add_action_cmd(f"CLRPFM {obj.lib}/{obj.name}", environment=da.Command_Type.QSYS, processing_step=da.Processing_Step.SAVE, stage=stage)

      savf = f"{self.meta_file.main_deploy_lib}/{lib['lib']}"
      savf_ifs_qsys = f"/qsys.lib/{self.meta_file.main_deploy_lib}.lib/{lib['lib']}.file"
      savf_ifs_target = f"{deployment_dir}/{lib['lib']}.file"

      actions.add_action_cmd(f"SAVLIB LIB({lib['lib']}) DEV(*SAVF) SAVF({savf}) \
            SELECT({includes}) DTACPR(*HIGH)", environment=da.Command_Type.QSYS, processing_step=da.Processing_Step.SAVE, stage=stage)

      cmd = f"CPYTOSTMF FROMMBR('{savf_ifs_qsys}') TOSTMF('{savf_ifs_target}') STMFOPT(*REPLACE)"
      actions.add_action_cmd(cmd=cmd, environment=da.Command_Type.QSYS, processing_step=da.Processing_Step.SAVE, stage=stage)

    self.meta_file.current_stages.get_stage(stage).set_status('prepare')
    self.meta_file.write_meta_file()



  def set_init_cmds_for_deployment(self, stage: str) -> None:
    """Prepare deployment on target system

      * Create deployment library
      * Create backup library
      * Create SAVF for each library which will be deployed to save old objects

    Args:
        stage (str): Run for this stage
    """
    
    actions = self.meta_file.actions

    actions.add_action_cmd(f"CRTLIB {self.meta_file.backup_deploy_lib}", environment=da.Command_Type.QSYS, 
        processing_step=da.Processing_Step.TARGET_PREPARE, stage=stage, check_error=False)

    actions.add_action_cmd(f"CRTLIB {self.meta_file.main_deploy_lib}", environment=da.Command_Type.QSYS, 
        processing_step=da.Processing_Step.TARGET_PREPARE, stage=stage, check_error=False)

    # Create save files for each lib to deploy
    for lib in self.meta_file.deploy_objects.get_lib_list_from_prod():
      actions.add_action_cmd(f"CRTSAVF {self.meta_file.backup_deploy_lib}/{lib}", 
          environment=da.Command_Type.QSYS, processing_step=da.Processing_Step.TARGET_PREPARE, stage=stage, check_error=False)
      actions.add_action_cmd(f"CLRSAVF {self.meta_file.backup_deploy_lib}/{lib}", 
        environment=da.Command_Type.QSYS, processing_step=da.Processing_Step.TARGET_PREPARE, stage=stage)

    self.meta_file.current_stages.get_stage(stage).set_status('prepare')
    self.meta_file.write_meta_file()



  def set_cmd_backup_objects_on_target(self, stage: str) -> None:
    """
     Save production objects bevore deployment
    """
    actions = self.meta_file.actions
    includes = ''
    clear_files = self.meta_file.current_stages.get_stage(stage).clear_files
    current_stage = self.meta_file.current_stages.get_stage(stage)

    for lib in self.meta_file.deploy_objects.get_lib_list_from_prod():

      for obj in self.meta_file.deploy_objects.get_obj_list_by_prod_lib(lib):
        includes += f" (*INCLUDE {obj.name} {obj.type})"

      actions.add_action_cmd(f"SAVLIB LIB({lib}) DEV(*SAVF) SAVF({self.meta_file.backup_deploy_lib}/{lib}) \
            SELECT({includes}) DTACPR(*HIGH)", 
            environment=da.Command_Type.QSYS, processing_step=da.Processing_Step.BACKUP_OLD_OBJ, stage=stage)

    self.meta_file.current_stages.get_stage(stage).set_status('prepare')
    self.meta_file.write_meta_file()



  def set_cmd_transfer_to_target(self, stage: str) -> None:
    """Transfer all SAVFs to the target system

    Args:
        stage (str): _description_
    Example:
        scp -rp /dir/deployment1 target_server:~/also-a-dir
    """

    current_stage = self.meta_file.current_stages.get_stage(stage)
    actions = self.meta_file.actions
    deployment_dir = os.path.dirname(os.path.realpath(self.meta_file.file_name))

    cmd = f"scp -rp {deployment_dir} {current_stage.host}:{current_stage.base_dir}"
    actions.add_action_cmd(cmd=cmd, environment=da.Command_Type.PASE, processing_step=da.Processing_Step.TRANSFER, stage=stage)



  def set_cmd_restore_objects_on_target(self, stage: str) -> None:
    """
     RSTLIB SAVLIB(PROUZALIB) DEV(*SAVF) SAVF(QGPL/PROUZASAVF) RSTLIB(RSTLIB)
            SELECT((*INCLUDE TEST *PGM) (*INCLUDE TEST *FILE)) 
    """
    actions = self.meta_file.actions
    clear_files = self.meta_file.current_stages.get_stage(stage).clear_files
    current_stage = self.meta_file.current_stages.get_stage(stage)
    deployment_dir = f"{current_stage.base_dir}/{os.path.basename(os.path.dirname(self.meta_file.file_name))}"

    for lib in self.meta_file.deploy_objects.get_lib_list_with_prod_lib():

      # Delete old savf
      cmd = f"DLTF FILE({self.meta_file.main_deploy_lib}/{lib['lib']})"
      actions.add_action_cmd(cmd=cmd, environment=da.Command_Type.QSYS, processing_step=da.Processing_Step.PERFORM_DEPLOYMENT, stage=stage)

      # Copy savf from IFS to QSYS file system
      savf = f"{self.meta_file.main_deploy_lib}/{lib['lib']}"
      savf_ifs_qsys = f"/qsys.lib/{self.meta_file.main_deploy_lib}.lib/{lib['lib']}.file"
      savf_ifs = f"{deployment_dir}/{lib['lib']}.file"

      cmd = f"CPYFRMSTMF FROMSTMF('{savf_ifs}') TOSTMF('{savf_ifs_qsys}') STMFOPT(*REPLACE)"
      actions.add_action_cmd(cmd=cmd, environment=da.Command_Type.QSYS, processing_step=da.Processing_Step.PERFORM_DEPLOYMENT, stage=stage)

      # Restore all objects
      restore_to_lib = lib['prod_lib']
      if current_stage.lib_replacement_necessary:
        if lib['prod_lib'] in current_stage.lib_mapping.keys():
          restore_to_lib = current_stage.lib_mapping[lib['lib']]

      includes = ''
      
      for obj in self.meta_file.deploy_objects.get_obj_list_by_lib(lib['lib']):
        includes += f" (*INCLUDE {obj.name} {obj.type})"

      actions.add_action_cmd(f"RSTLIB SAVLIB({lib['lib']}) DEV(*SAVF) SAVF({self.meta_file.main_deploy_lib}/{lib['lib']}) \
            SELECT({includes}) RSTLIB({restore_to_lib})", 
            environment=da.Command_Type.QSYS, processing_step=da.Processing_Step.PERFORM_DEPLOYMENT, stage=stage)

    self.meta_file.current_stages.get_stage(stage).set_status('prepare')
    self.meta_file.write_meta_file()



  def set_cmds(self, stage: str):

    cmd_mapping = {
      da.Processing_Step.PRE:
        [
        ],
      da.Processing_Step.POST:
        [
        ],
      da.Processing_Step.SAVE: 
        [
          self.set_init_cmds_for_save, 
          self.set_cmd_object_to_savf
        ],
      da.Processing_Step.TRANSFER:
        [
          self.set_cmd_transfer_to_target
        ],
      da.Processing_Step.TARGET_PREPARE:
        [
          self.set_init_cmds_for_deployment
        ],
      da.Processing_Step.BACKUP_OLD_OBJ:
        [
          self.set_cmd_backup_objects_on_target
        ],
      da.Processing_Step.PERFORM_DEPLOYMENT:
        [
          self.set_cmd_restore_objects_on_target
        ]
      }
    
    with open(constants.C_STAGE_COMMANDS, "r") as file:
      stage_cmds = json.load(file)

    do_steps = self.meta_file.current_stages.get_stage(stage).processing_steps
    actions = self.meta_file.actions

    for k, v in cmd_mapping.items():

      if k.value not in do_steps:
        continue

      for cmd in v:
        cmd(stage)

      for sc in stage_cmds:
        if len(sc['stages']) == 0 or stage in sc['stages'] and k.value == sc['processing_step']:
          actions.add_action_cmd(cmd=sc['cmd'], environment=sc['environment'], 
                processing_step=sc['processing_step'], stage=stage, check_error=sc['check_error'])



  def get_all_attributes(self, processing_step: str=None, stage: str=None) -> {}:
    dict = {
      'processing_step': processing_step,
      'stage': s.Stage.get_stage(stage).get_dict()
    }

    dict['meta_file'] = self.meta_file.get_all_data_as_dict()

    return dict



  def run_commands(self, processing_step: str=None, stage: str=None) -> None:

    all_attributes = self.get_all_attributes(processing_step=processing_step, stage=stage)

    self.meta_file.current_stages.get_stage(stage).set_status('in process')

    for action in self.meta_file.get_actions(processing_step=processing_step, stage=stage):

      cmd = action.cmd.format(**all_attributes)

      if action.environment == da.Command_Type.QSYS:
        cmd = f'(cl -v "{cmd}"; cl -v "dspjoblog")'


      print(f"run {cmd}")
      
      s=subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, check=False, executable='/bin/bash')
      stdout = s.stdout
      stderr = s.stderr

      if constants.C_CONVERT_OUTPUT:
        stdout = stdout.decode(constants.C_CONVERT_FROM)
        stderr = stderr.decode(constants.C_CONVERT_FROM)

      run_history = rh.Run_History(stage=stage)
      action.run_history.add_history(run_history)

      run_history.stdout = stdout
      run_history.stderr = stderr

      if s.returncode != 0:
        
        print(stderr)
        run_history.status = 'failed'
        
        if action.check_error is False:
          continue

        self.meta_file.current_stages.get_stage(stage).set_status('failed')
        self.meta_file.write_meta_file()
        raise Exception(stderr)

      self.meta_file.current_stages.get_stage(stage).set_status('finished')
      run_history.status = 'finished'
    
    self.meta_file.write_meta_file()

    #iconv -f IBM-1252 -t utf-8 './logs/prouzalib/date.sqlrpgle.srvpgm.error.log' > './logs/prouzalib/date.sqlrpgle.srvpgm.error.log'_tmp && mv './logs/prouzalib/date.sqlrpgle.srvpgm.error.log'_tmp './logs/prouzalib/date.sqlrpgle.srvpgm.error.log' 
