"""
DB deployment: deploys changes of large tables with a minimal downtime (see docs/db-deployment.md)

As processing steps:

  {"processing_step": "db-prepare", "environment": "SCRIPT", "execute": "db_deployment.prepare_tables", "check_error": true}
  {"processing_step": "db-copy", "environment": "SCRIPT", "execute": "db_deployment.copy_tables", "check_error": true}
  {"processing_step": "db-cutover", "environment": "SCRIPT", "execute": "db_deployment.cutover_tables", "check_error": true}
  {"processing_step": "db-cleanup", "environment": "SCRIPT", "execute": "db_deployment.cleanup_tables", "check_error": true}

* prepare_tables:  build the new tables in the shadow library, start journaling
* copy_tables:     copy the rows while the users keep working, catch up with their changes
* cutover_tables:  apply the last changes and replace the old tables (in the maintenance window)
* cleanup_tables:  remove the shadow library

The tables are configured in the custom data of the deployment: {"db_deployment": {"tables": [...]}}
"""
from __future__ import annotations
import logging

from modules import meta_file as mf, stages as s
from modules import deploy_action as da
from modules.db_deployment import connection, objects, prepare, sync, cutover, cleanup



def run_for_tables(meta_file: mf.Meta_File, stage_obj: s.Stage, step: str, function) -> None:

    tables = objects.get_table_configs(meta_file)
    if len(tables) == 0:
        logging.info(f"No tables configured for the DB deployment (custom data: db_deployment.tables), nothing to do for {step}")
        return

    config = connection.load_config()
    db = connection.connect(config, stage_obj.host)

    try:
        for table in tables:
            logging.info(f"{step}: {table['lib']}/{table['name']}")
            function(db, table, connection.get_settings(config, table))
    finally:
        db.close()



def prepare_tables(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:

    def run(db, table, settings):
        deploy_objects = prepare.prepare_table(db, meta_file, table, settings)
        objects.set_status(deploy_objects, objects.C_PREPARED)
        meta_file.save()

    run_for_tables(meta_file, stage_obj, 'db-prepare', run)



def copy_tables(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:

    shadow_lib = objects.get_shadow_lib(meta_file)

    run_for_tables(meta_file, stage_obj, 'db-copy',
                   lambda db, table, settings: sync.copy_table(db, shadow_lib, table, settings))



def cutover_tables(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:

    def run(db, table, settings):
        replaced = cutover.cutover_table(db, meta_file, table, settings)
        deploy_objects = [o for o in (objects.get_deploy_object(meta_file, r.prod_lib, r.name) for r in replaced if r.origin == 'deployment')
                          if o is not None]
        objects.set_status(deploy_objects, objects.C_DEPLOYED)
        meta_file.save()

    run_for_tables(meta_file, stage_obj, 'db-cutover', run)



def cleanup_tables(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:

    tables = objects.get_table_configs(meta_file)
    if len(tables) == 0:
        logging.info("No tables configured for the DB deployment, nothing to clean up")
        return

    config = connection.load_config()
    db = connection.connect(config, stage_obj.host)

    try:
        cleanup.cleanup(db, meta_file, tables)
    finally:
        db.close()
