import logging
import inspect
from pathlib import Path
import sys, os
from sys import path

#########################################
# Logger Configuration
#########################################

LOG_FORMAT = '%(asctime)s (%(process)d) %(levelname)-7.7s %(filename)-10.10s %(funcName)-10.10s (%(lineno)d): %(message)s'

LOG_LEVEL = logging.INFO

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

# exist_ok: processes which start at the same time (gunicorn workers, processing services) create it together
os.makedirs(LOG_DIR, exist_ok=True)

# Larger than C_LOG_MAX_MB: renamed to .1, .2, ... (docs/features/data-retention.md)
try:
    from etc import constants
    from modules import log_rotation
    log_rotation.rotate_at_start(str(Path(LOG_DIR, f"{LOG_NAME}.log")), constants.C_LOG_MAX_MB, constants.C_LOG_BACKUPS)
except Exception as e:
    print(f"Log file not rotated: {e}")

file_handler = logging.FileHandler(filename=Path(LOG_DIR, f"{LOG_NAME}.log"))
#stdout_handler = logging.StreamHandler(stream=sys.stdout)
handlers = [file_handler]

logging.basicConfig(format=LOG_FORMAT, level=LOG_LEVEL, handlers=handlers)
