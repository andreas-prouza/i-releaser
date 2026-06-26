import glob
import json
import logging
import os

from etc.constants import C_LOCAL_BASE_DIR
from modules.meta_file import Meta_File
from modules.meta_file_db import init_db, upsert_meta_file


def search_and_store_meta_files():
    """
    Searches for all meta files and stores them in the database.
    """
    logging.info("Initializing and populating meta file database...")
    init_db()

    meta_dir = os.path.join(C_LOCAL_BASE_DIR, "meta")
    search_pattern = os.path.join(meta_dir, "**", "deployment_*.json")

    for file_path in glob.glob(search_pattern, recursive=True):
        try:
            logging.debug(f"Processing meta file: {file_path}")
            meta_file = Meta_File._load_json_file_internal(file_path)
            if meta_file:
                upsert_meta_file(meta_file)
                logging.debug(f"Stored meta file in DB: {file_path}")
        except Exception as e:
            logging.error(f"Failed to process or store meta file {file_path}: {e}", stack_info=True)
    logging.info("Meta file database initialization and population complete.")
