#######################################################
# Processing service
#
#   Runs the stages of deployments independent of the web app.
#   Start it with: ./service start
#
#   See docs/processing-service.md
#######################################################

import sys, os

base_dir = os.path.realpath(os.path.dirname(__file__)+"/..")
webapp_dir = os.path.join(base_dir, 'webapp')

# Same environment as for a stage which is run by the web app:
# its working directory and its configs (webapp/etc) are available for the steps and scripts
sys.path.insert(0, base_dir)
sys.path.append(webapp_dir)
os.chdir(webapp_dir)

from etc import logger_config
import logging

from modules import processing_service
# Loads the scripts, so they don't need to be loaded by each job
from modules import ibm_i_commands
from modules.db import app_sqlite




if __name__ == '__main__':

    logging.info("Run processing service")

    app_sqlite.create_tables()

    try:
        processing_service.Service().run_forever()

    except processing_service.ServiceAlreadyRunningException as e:
        logging.error(e)
        print(e, file=sys.stderr)
        sys.exit(1)
