import logging, sys
from io import StringIO

from etc import logger_config, constants

logging.info('Test Start')

#stdout_orig = sys.stdout
#stdout_new = StringIO()
#sys.stdout = stdout_new
#stderr_orig = sys.stderr
#sys.stderr = stderr_new = StringIO()
hdl = logging.StreamHandler(stream=sys.stdout)
logging.getLogger().addHandler(hdl)

logging.info(logging._handlerList)

logging.info('Test Mitte')

logging.getLogger().removeHandler(hdl)

logging.info('Test Ende')