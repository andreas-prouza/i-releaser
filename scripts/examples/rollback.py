from __future__ import annotations
import os, logging

from etc import constants
from modules import action_type, deploy_version, ibm_i_commands, meta_file as mf, stages as s
from modules import deploy_action as da
from modules.object_status import Status as Obj_Status


def get_objects_from_origin(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:

    project = meta_file.custom_data.get('project')
    version = meta_file.custom_data.get('version')

    if not project or not version:
        msg = f"Project ({project}) or version ({version}) information is missing in meta file's custom data."
        logging.error(msg)
        raise ValueError(msg)

    dv = deploy_version.Deploy_Version.get_deployment(project, version)
    logging.debug(f"{dv=}")

    mf_orig = mf.Meta_File.load_json_file(dv['meta_file'])

    action_type.create_action_log(action=action_type.Action_type.CUSTOM_ACTION, details=f"Rollback of deployment started in Project {meta_file.project}, Version {meta_file.deploy_version}", meta_file=mf_orig, stage=stage_obj)
    mf_orig.write_meta_file()

    meta_file.deploy_objects = mf_orig.deploy_objects

    for obj in meta_file.deploy_objects:
        if obj.deploy_status not in [Obj_Status.FINISHED, Obj_Status.RESTORED]:
            meta_file.deploy_objects.remove(obj)
        obj.deploy_status = Obj_Status.NEW




def restore_objects(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:

    project = meta_file.custom_data.get('project')
    version = meta_file.custom_data.get('version')
    
    if not project or not version:
        msg = f"Project ({project}) or version ({version}) information is missing in meta file's custom data."
        logging.error(msg)
        raise ValueError(msg)

    dv = deploy_version.Deploy_Version.get_deployment(project, version)
    logging.debug(f"{dv=}")

    mf_orig = mf.Meta_File.load_json_file(dv['meta_file'])

    last_added_action = action
    cmd = ibm_i_commands.IBM_i_commands(meta_file)

    meta_file.deploy_objects.set_objects_status(Obj_Status.IN_RESTORE)
    app_prod_backup_lib = mf_orig.backup_deploy_lib

    for obj in meta_file.deploy_objects:

        if not obj.ready:
            continue

        restore_to_lib = obj.prod_lib
        if stage_obj.lib_replacement_necessary:
            if obj.prod_lib in stage_obj.lib_mapping.keys():
                restore_to_lib = stage_obj.lib_mapping[obj.lib]
        restore_to_lib = restore_to_lib.replace('$', '\\$')

        last_added_action = action.sub_actions.add_action(da.Deploy_Action(
          #cmd=f"RSTLIB SAVLIB({lib['lib']}) DEV(*SAVF) SAVF({meta_file.remote_deploy_lib}/{lib['lib']}) SELECT({includes}) RSTLIB({restore_to_lib})", 
          cmd=f"CALL DEVOPS/RSTOBJ PARM({restore_to_lib} {obj.name.replace('$', '\\$')} {app_prod_backup_lib} {restore_to_lib} {restore_to_lib})", 
          environment=da.Command_Type.QSYS, 
          processing_step=action.processing_step, 
          stage=stage_obj.name, 
          run_in_new_job=True,
          check_error=action.check_error
        ))
        cmd.execute_action(stage=stage_obj, action=last_added_action)

    action_type.create_action_log(action=action_type.Action_type.CUSTOM_ACTION, details=f"Rollback of deployment completed in Project {meta_file.project}, Version {meta_file.deploy_version}", meta_file=mf_orig, stage=stage_obj)
    mf_orig.write_meta_file()

    meta_file.deploy_objects.set_objects_status(Obj_Status.RESTORED)
    meta_file.write_meta_file()
