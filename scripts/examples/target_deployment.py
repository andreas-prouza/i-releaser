import os

from etc import constants
from modules import meta_file as mf, stages as s
from modules import deploy_action as da
from modules.cmd_status import Status as Cmd_Status
from modules.object_status import Status as Obj_Status
from modules import ibm_i_commands
from modules.db_deployment import objects as db_objects


def restore_objects_on_target(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:
    """
     RSTLIB SAVLIB(MYLIB) DEV(*SAVF) SAVF(QGPL/MYSAVF) RSTLIB(RSTLIB)
            SELECT((*INCLUDE TEST *PGM) (*INCLUDE TEST *FILE)) 

     Expects the save files of `save_objects.py` in the directory of the deployment.
    """


    actions = stage_obj.actions

    clear_files = stage_obj.clear_files
    deployment_dir = os.path.dirname(os.path.realpath(meta_file.meta_dir))
    last_added_action = action
    cmd = ibm_i_commands.IBM_i_commands(meta_file)

    meta_file.deploy_objects.set_objects_status(Obj_Status.IN_RESTORE)

    for lib in meta_file.deploy_objects.get_lib_list_with_prod_lib(ready=True, objects_only=True):

      last_added_action = action.sub_actions.add_action(da.Deploy_Action(
        cmd=f"CRTSAVF {meta_file.remote_deploy_lib}/{lib['lib']}",
        environment=da.Command_Type.QSYS,
        processing_step=action.processing_step,
        stage=stage_obj.name,
        check_error=False
      ))
      cmd.execute_action(stage=stage_obj, action=last_added_action)

      last_added_action = action.sub_actions.add_action(da.Deploy_Action(
        cmd=f"CLRSAVF {meta_file.remote_deploy_lib}/{lib['lib']}",
        environment=da.Command_Type.QSYS,
        processing_step=action.processing_step,
        stage=stage_obj.name,
        check_error=action.check_error
      ))
      cmd.execute_action(stage=stage_obj, action=last_added_action)

      # Copy savf from IFS to QSYS file system
      savf = f"{meta_file.remote_deploy_lib}/{lib['lib']}"
      savf_ifs_qsys = f"/qsys.lib/{meta_file.remote_deploy_lib}.lib/{lib['lib']}.file"
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
        restore_to_lib = stage_obj.lib_mapping.get(lib['prod_lib'], restore_to_lib)

      includes = ''
      
      for obj in meta_file.deploy_objects.get_obj_list_by_prod_lib(lib['prod_lib'], ready=True, objects_only=True):

        # Replaced by the cut-over. Raises an error if the cut-over hasn't been done yet.
        if db_objects.check_deploy_object(meta_file, obj):
          continue

        obj_type = obj.attribute if obj.type == 'obj' else obj.type
        includes += f" (*INCLUDE {obj.name} *{obj_type})"

      if includes == '':
        continue

      last_added_action = action.sub_actions.add_action(da.Deploy_Action(
        cmd=f"RSTLIB SAVLIB({lib['lib']}) DEV(*SAVF) SAVF({meta_file.remote_deploy_lib}/{lib['lib']}) SELECT({includes}) MBROPT(*ALL) ALWOBJDIF(*ALL) RSTLIB({restore_to_lib})", 
        environment=da.Command_Type.QSYS, 
        processing_step=action.processing_step, 
        stage=stage_obj.name, 
        run_in_new_job=True,
        check_error=action.check_error
      ))
      cmd.execute_action(stage=stage_obj, action=last_added_action)

    meta_file.deploy_objects.set_objects_status(Obj_Status.RESTORED)
    meta_file.save()
