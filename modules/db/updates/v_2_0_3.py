import logging
import os
from modules.db import app_sqlite
import sqlite3



def add_parallel_deployment_execution_allowed():

    logging.info("Adding parallel_deployment_execution_allowed column if not exists...")
        
    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()

        try:
            c.execute("ALTER TABLE meta_files ADD COLUMN parallel_deployment_execution_allowed BOOLEAN")

        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logging.warning(f"Could not add parallel_deployment_execution_allowed column: {e}")
                return
            raise e







def add_immediate_execution():

    logging.info("Adding run_immediate column if not exists...")
    
    with app_sqlite.get_db_connection() as conn:
        c = conn.cursor()

        try:
            c.execute("ALTER TABLE stages ADD COLUMN run_immediate BOOLEAN")

        except sqlite3.OperationalError as e:
            # Check if the error string contains the specific SQLite message
            if "duplicate column name" in str(e).lower():
                logging.warning(f"Could not add run_immediate column: {e}")
                return
            
            raise e
