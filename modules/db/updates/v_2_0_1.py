import logging
from modules.db import app_sqlite
from modules.db import compression



def is_uncompressed_text(value) -> bool:
    return bool(value) and isinstance(value, str) and not value.startswith("file://")



def add_compression():

    logging.info("Starting compression of text fields in the database...")

    with app_sqlite.get_db_connection() as conn:

        c = conn.cursor()


        ########################################
        # meta_files
        ########################################
        c.execute("SELECT id, custom_data FROM meta_files")
        rows = c.fetchall()

        update_data = []

        # 2. Loop through the rows and compress the text
        for rowid, custom_data in rows:

            if not custom_data or isinstance(custom_data, bytes):
                continue  # Skip if custom_data is None, empty or already compressed

            compressed_custom_data = compression.compress_field(custom_data)

            # Append a tuple formatted for our UPDATE statement: (val1, id)
            update_data.append((compressed_custom_data, rowid))

        # 3. Batch update the table with the new BLOB (binary) data
        c.executemany("UPDATE meta_files SET custom_data = ? WHERE id = ?", update_data)


        ########################################
        # workflow_definitions
        ########################################
        c.execute("SELECT id, definition FROM workflow_definitions")
        rows = c.fetchall()

        update_data = []

        # 2. Loop through the rows and compress the text
        for rowid, definition in rows:

            if not definition or isinstance(definition, bytes):
                continue  # Skip if definition is None, empty or already compressed

            compressed_definition = compression.compress_field(definition)

            # Append a tuple formatted for our UPDATE statement: (val1, id)
            update_data.append((compressed_definition, rowid))

        # 3. Batch update the table with the new BLOB (binary) data
        c.executemany("UPDATE workflow_definitions SET definition = ? WHERE id = ?", update_data)



        ########################################
        # run_history
        ########################################
        c.execute("SELECT id, log FROM run_history")
        rows = c.fetchall()

        update_data = []

        # 2. Loop through the rows and compress the text
        for rowid, log in rows:

            if not log or isinstance(log, bytes) or log.startswith("file://"):
                continue  # Skip if log is None, empty, already compressed or stored in a file
            
            compressed_log = compression.compress_field(log)

            # Append a tuple formatted for our UPDATE statement: (val1, id)
            update_data.append((compressed_log, rowid))

        # 3. Batch update the table with the new BLOB (binary) data
        c.executemany("UPDATE run_history SET log = ? WHERE id = ?", update_data)


        ########################################
        # action_run_history
        ########################################
        c.execute("SELECT id, stdout, stderr FROM action_run_history")
        rows = c.fetchall()

        update_data = []

        # 2. Loop through the rows and compress the text
        for rowid, stdout, stderr in rows:

            if not is_uncompressed_text(stdout) and not is_uncompressed_text(stderr):
                continue  # Skip if both stdout and stderr are None, empty, already compressed or stored in a file

            compressed_stdout = compression.compress_field(stdout) if is_uncompressed_text(stdout) else stdout
            compressed_stderr = compression.compress_field(stderr) if is_uncompressed_text(stderr) else stderr

            logging.info(f"bevore Compressing action_run_history id={rowid}: stdout size={len(stdout) if stdout else 0}, stderr size={len(stderr) if stderr else 0}")
            logging.info(f"after Compressing action_run_history id={rowid}: stdout size={len(compressed_stdout) if compressed_stdout else 0}, stderr size={len(compressed_stderr) if compressed_stderr else 0}")
            
            # Append a tuple formatted for our UPDATE statement: (val1, val2, id)
            update_data.append((compressed_stdout, compressed_stderr, rowid))

        # 3. Batch update the table with the new BLOB (binary) data
        c.executemany("UPDATE action_run_history SET stdout = ?, stderr = ? WHERE id = ?", update_data)




        #################################################
        # Commit the transaction and close the connection
        #################################################

        conn.commit()


        #################################################
        # Reclaim space after compression
        #################################################
        c.execute("VACUUM")



