import logging
import os
from modules.db import app_sqlite
from modules.db import compression
from modules import files


def extract_logs_2_meta_dir():
    logging.info("Moving logs to meta directory...")

    
    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()


        ###################################################
        # Run_History
        ###################################################

        c.execute("""select rh.*, mf.meta_dir  from meta_files mf
                        left join run_history rh on rh.meta_file_id = mf.id 
                     where rh.log is not null and rh.log <> '' and mf.meta_dir is not null and mf.meta_dir <> '' """)
        rows = c.fetchall()

        for row in rows:

            if row['log'] is None or len(row['log']) == 0 or (isinstance(row['log'], str) and row['log'].startswith("file://")):
                continue  # Skip if log is None or empty

            meta_dir = row['meta_dir']
            id = row['id']
            log_file_path = os.path.join(meta_dir, "logs", "run_history", f"{id}.log")
            log = compression.decompress_field(row['log'])

            # Write the combined logs to the processing.log file in the meta directory
            os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
            files.writeText(log, log_file_path)

            c.execute("UPDATE run_history SET log = ? where id = ?", (f"file://{log_file_path}", id))


        ###################################################
        # Action_Run_History
        ###################################################

        c.execute("""select arh.*, mf.meta_dir  from meta_files mf
                        INNER join deploy_objects do on do.meta_file_id = mf.id 
                        INNER join actions a on a.deploy_object_id  = do.id
                        INNER join action_run_history arh on arh.action_id = a.id
                    where mf.meta_dir is not null and mf.meta_dir <> ''
                    union all
                    select arh.*, mf.meta_dir  from meta_files mf
                        INNER join stages s on s.meta_file_id = mf.id 
                        INNER join actions a on a.stage_id = s.id
                        INNER join action_run_history arh on arh.action_id = a.id
                    where mf.meta_dir is not null and mf.meta_dir <> ''
                    union all
                    select arh.*, mf.meta_dir  from meta_files mf
                        INNER join stages s on s.meta_file_id = mf.id 
                        INNER join actions a on a.stage_id = s.id
                        inner join actions a2 on a2.action_id = a.id
                        INNER join action_run_history arh on arh.action_id = a2.id
                    where mf.meta_dir is not null and mf.meta_dir <> '' """)
        rows = c.fetchall()

        for row in rows:

            meta_dir = row['meta_dir']
            id = row['id']

            if row['stdout'] is not None and len(row['stdout']) > 0 and not (isinstance(row['stdout'], str) and row['stdout'].startswith("file://")):
                stdout_file_path = os.path.join(meta_dir, "logs", "action_run_history", f"{id}_stdout.log")
                os.makedirs(os.path.dirname(stdout_file_path), exist_ok=True)
                files.writeText(compression.decompress_field(row['stdout']), stdout_file_path)
                c.execute("UPDATE action_run_history SET stdout = ? where id = ?", (f"file://{stdout_file_path}", id))

            if row['stderr'] is not None and len(row['stderr']) > 0 and not (isinstance(row['stderr'], str) and row['stderr'].startswith("file://")):
                stderr_file_path = os.path.join(meta_dir, "logs", "action_run_history", f"{id}_stderr.log")
                os.makedirs(os.path.dirname(stderr_file_path), exist_ok=True)
                files.writeText(compression.decompress_field(row['stderr']), stderr_file_path)
                c.execute("UPDATE action_run_history SET stderr = ? where id = ?", (f"file://{stderr_file_path}", id))



        #################################################
        # Commit the transaction and close the connection
        #################################################

        conn.commit()


        #################################################
        # Reclaim space after compression
        #################################################
        c.execute("VACUUM")

