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

# Configures the log (an import for its side effect)
from etc import logger_config  # noqa: F401
import logging

from modules import processing_service
from modules import scripts_loader, settings_check
from modules import errors
from modules.db import app_sqlite




if __name__ == '__main__':

    logging.info("Run processing service")

    app_sqlite.create_tables()

    # Loaded once, so each job process has them already. A script with an error only fails its steps.
    scripts_loader.preload()

    try:
        settings_check.check_at_start()
        # The database is updated by the web app
        app_sqlite.check_schema_version()
        processing_service.Service().run_forever()

    except (processing_service.ServiceAlreadyRunningException, errors.App_Error, settings_check.Invalid_Setting_Error) as e:
        logging.error(e)
        print(e, file=sys.stderr)
        sys.exit(1)
