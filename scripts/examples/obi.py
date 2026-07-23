from __future__ import annotations
import logging
from pathlib import Path
import shutil

from modules import ibm_i_commands, meta_file as mf, stages as s
from modules import deploy_action as da
from modules import deploy_object as do
from modules.object_status import Status as Obj_Status


def load_objects_from_compile_list(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:

    compiles = meta_file.custom_data.get('compiles')

    if not compiles:
        msg = "Compile list is missing in meta file's custom data."
        logging.error(msg)
        raise ValueError(msg)

    for compile_level in compiles:

        for source_item in compile_level['sources']:

            if 'ignore' in source_item and source_item['ignore']:
                logging.info(f"Source {source_item['source']} ignored")
                continue
            
            if source_item['status'] != 'success':
                logging.info(f"Source {source_item['source']} is not successful, skip adding build commands")
                continue

            if source_item['source'].split('.')[-1] == 'cpy':
                logging.info(f"Copy source {source_item['source']} detected, skip adding build commands")
                continue
            
            variables = source_item.get('variables', {})
            target_lib_mapping = variables.get('TARGET_LIB_MAPPING', {})
            prod_lib = next((k for k, v in target_lib_mapping.items() if v == variables['TARGET_LIB']), variables['TARGET_LIB'])
            source_only = source_item.get('source', '').endswith(('.sqltable.file', '.sqlview.file', '.sqlindex.file', '.lf.file', '.pf.file'))

            # Copy source to meta_dir
            if source_item.get('source', None):
                source_file = Path(source_item.get('source', None))
                source_file_absolut = Path(source_item['absolute_path'])
                destination_base = Path(meta_file.meta_dir) / Path('src')

                dest_dir = destination_base / source_file.parent
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file_absolut, destination_base / source_file)

            logging.debug(f"Processing source item: {source_item}")
            obj = do.Deploy_Object(level=compile_level['level'],
                                    prod_lib=prod_lib, 
                                    lib=variables['TARGET_LIB'], 
                                    name=variables['OBJ_NAME'], 
                                    type=variables['SRC_TYPE'], 
                                    attribute=variables['SRC_ATTR'],
                                    source=source_item.get('source', None),
                                    source_only=source_only
                                )
            logging.debug(f"Adding deploy object: {obj.get_dict()}")
            meta_file.add_deploy_object(obj)
            meta_file.save()
            logging.debug(f"After adding deploy object: {obj.get_dict()}")
            





def perform_deployment(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:

    execution = {
        '.lf.file': deploy_lf,
        '.pf.file': deploy_pf,
        '.sqltable.file': execute_sql_script,
        '.sqlview.file': execute_sql_script,
        '.sqlindex.file': execute_sql_script
    }

    deployment_dir = meta_file.meta_dir
    last_added_action = action
    cmd = ibm_i_commands.IBM_i_commands(meta_file)

    meta_file.deploy_objects.set_objects_status(Obj_Status.IN_RESTORE)

    copy_all_savf_from_stmf(meta_file=meta_file, stage_obj=stage_obj, action=last_added_action)

    for obj in meta_file.deploy_objects.get_obj_list_sorted_by_level():

        if obj.deploy_status == Obj_Status.FINISHED:
            logging.info(f"Object {obj.name} already deployed, skipping")
            continue

        logging.info(f"Deploying object {obj.name} of type {obj.type} in lib {obj.lib}")
        extension = f".{obj.attribute}.{obj.type}"

        execution.get(extension, restore_object)(meta_file=meta_file, stage_obj=stage_obj, action=last_added_action, object=obj)
        obj.deploy_status = Obj_Status.FINISHED

        meta_file.save()

        



def copy_all_savf_from_stmf(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action):

    deployment_dir = meta_file.meta_dir
    last_added_action = action
    cmd = ibm_i_commands.IBM_i_commands(meta_file)

    for lib in meta_file.deploy_objects.get_lib_list_with_prod_lib(objects_only=True):
    
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



def restore_object(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action, object: do.Deploy_Object) -> None:

    deployment_dir = meta_file.meta_dir
    last_added_action = action
    cmd = ibm_i_commands.IBM_i_commands(meta_file)

    # Restore all objects
    restore_to_lib = object.prod_lib

    if stage_obj.lib_replacement_necessary:
        if object.prod_lib in stage_obj.lib_mapping.keys():
            restore_to_lib = stage_obj.lib_mapping[object.lib]
      
    obj_name = object.name.replace('$', '\\$')

    last_added_action = action.sub_actions.add_action(da.Deploy_Action(
        cmd=f"RSTOBJ OBJ({obj_name}) SAVLIB({object.lib}) DEV(*SAVF) SAVF({meta_file.remote_deploy_lib}/{object.lib}) RSTLIB({restore_to_lib})", 
        environment=da.Command_Type.QSYS, 
        processing_step=action.processing_step, 
        stage=stage_obj.name, 
        run_in_new_job=True,
        check_error=action.check_error
    ))
    
    cmd.execute_action(stage=stage_obj, action=last_added_action)



def deploy_lf(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action, object: do.Deploy_Object) -> None:

    deployment_dir = meta_file.meta_dir
    last_added_action = action
    cmd = ibm_i_commands.IBM_i_commands(meta_file)

    # Restore all objects
    restore_to_lib = object.prod_lib

    if stage_obj.lib_replacement_necessary:
        if object.prod_lib in stage_obj.lib_mapping.keys():
            restore_to_lib = stage_obj.lib_mapping[object.lib]
      
    obj_name = object.name.replace('$', '\\$')

    last_added_action = action.sub_actions.add_action(da.Deploy_Action(
        cmd=f"""cl -v "CRTSRCPF FILE(QTEMP/QSRC) RCDLEN(112)" 2> /dev/null;
                cl -v "CPYFRMSTMF FROMSTMF('"'src/{object.source}'"') TOMBR('/QSYS.LIB/QTEMP.LIB/QSRC.FILE/"'{obj_name}'".MBR') MBROPT(*replace)";
                cl -v "DLTF FILE('{restore_to_lib}/{obj_name}')" 2> /dev/null;
                cl -v "CRTLF FILE("'{restore_to_lib}/{obj_name}'") SRCFILE(QTEMP/QSRC) OPTION(*EVENTF)";
                """, 
        environment=da.Command_Type.PASE, 
        processing_step=action.processing_step, 
        stage=stage_obj.name, 
        run_in_new_job=True,
        check_error=action.check_error
    ))
    cmd.execute_action(stage=stage_obj, action=last_added_action)

    
    

def deploy_pf(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action, object: do.Deploy_Object) -> None:

    deployment_dir = meta_file.meta_dir
    last_added_action = action
    cmd = ibm_i_commands.IBM_i_commands(meta_file)

    # Restore all objects
    restore_to_lib = object.prod_lib

    if stage_obj.lib_replacement_necessary:
        if object.prod_lib in stage_obj.lib_mapping.keys():
            restore_to_lib = stage_obj.lib_mapping[object.lib]
      
    obj_name = object.name.replace('$', '\\$')

    last_added_action = action.sub_actions.add_action(da.Deploy_Action(
        cmd=f"""cl -v "CRTSRCPF FILE(QTEMP/QSRC) RCDLEN(112)" 2> /dev/null;
                cl -v "CPYFRMSTMF FROMSTMF('"'src/{object.source}'"') TOMBR('/QSYS.LIB/QTEMP.LIB/QSRC.FILE/"'{obj_name}'".MBR') MBROPT(*replace)";
                cl -v "CRTPF FILE("'{restore_to_lib}/{obj_name}'") SRCFILE(QTEMP/QSRC) OPTION(*EVENTF)" 2> /dev/null;
                cl -v "CHGPF FILE("'{restore_to_lib}/{obj_name}'") SRCFILE(QTEMP/QSRC) OPTION(*EVENTF)";
                """, 
        environment=da.Command_Type.PASE, 
        processing_step=action.processing_step, 
        stage=stage_obj.name, 
        run_in_new_job=True,
        check_error=action.check_error
    ))
    cmd.execute_action(stage=stage_obj, action=last_added_action)

    

def execute_sql_script(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action, object: do.Deploy_Object) -> None:

    deployment_dir = meta_file.meta_dir
    last_added_action = action
    cmd = ibm_i_commands.IBM_i_commands(meta_file)

    # Restore all objects
    restore_to_lib = object.prod_lib

    if stage_obj.lib_replacement_necessary:
        if object.prod_lib in stage_obj.lib_mapping.keys():
            restore_to_lib = stage_obj.lib_mapping[object.lib]
      
    obj_name = object.name.replace('$', '\\$')

    last_added_action = action.sub_actions.add_action(da.Deploy_Action(
        cmd=f"""export OBI_CONTENT="$(sed 's/{restore_to_lib}/{object.lib}/g' src/{object.source})";
                printf '%s' "$OBI_CONTENT" > src/{object.source};
                cl -v "RUNSQLSTM SRCSTMF('"'src/{object.source}'"') COMMIT(*NONE) ERRLVL(21)"
                """, 
        environment=da.Command_Type.PASE, 
        processing_step=action.processing_step, 
        stage=stage_obj.name, 
        run_in_new_job=True,
        check_error=action.check_error,
        cwd=deployment_dir
    ))
    cmd.execute_action(stage=stage_obj, action=last_added_action)

    
    