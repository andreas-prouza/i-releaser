import logging
import inspect
from pathlib import Path
import os
from sys import path
import threading

#########################################
# Logger Configuration
#########################################

def thread_id_filter(record):
    """Inject thread_id to log records"""
    record.thread_id = threading.get_native_id()
    return record


LOG_FORMAT = '%(asctime)s (%(process)d)|%(thread_id)d %(levelname)-7.7s %(filename)-10.10s %(funcName)-10.10s (%(lineno)d): %(message)s'

LOG_LEVEL = logging.DEBUG

LOG_DIR = Path(os.path.dirname(__file__), '../log')

# None: As default the callers Script name will be used
LOG_NAME = None


#########################################
# Set logger 
#########################################

# File name from callers file
if LOG_NAME is None:

    for stack in inspect.stack()[1:]:

        if not stack.filename.startswith('<'):

            LOG_NAME = Path(stack.filename).stem
            break

# File name from current file
# current_file = os.path.splitext(os.path.abspath(__file__))[0]

if not Path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

logging.basicConfig(format=LOG_FORMAT, filename=Path(LOG_DIR, LOG_NAME), level=LOG_LEVEL)
#logging.getLogger().addFilter(thread_id_filter)

# Get the root logger
root_logger = logging.getLogger()

# FIX: Attach the filter to all handlers on the root logger, 
# ensuring all propagating logs get the thread_id injected.
for handler in root_logger.handlers:
    handler.addFilter(thread_id_filter)
