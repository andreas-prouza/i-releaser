import logging
import inspect
from pathlib import Path
import sys, os
from sys import path

#########################################
# Logger Configuration
#########################################

LOG_FORMAT = '%(asctime)s %(levelname)-7.7s %(filename)-10.10s %(funcName)-10.10s (%(lineno)d): %(message)s'

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

file_handler = logging.FileHandler(filename=Path(LOG_DIR, f"{LOG_NAME}.log"))
#stdout_handler = logging.StreamHandler(stream=sys.stdout)
handlers = [file_handler]

logging.basicConfig(format=LOG_FORMAT, level=LOG_LEVEL, handlers=handlers)
