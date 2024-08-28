# Standard library imports
import bisect
import configparser
import logging
import sys
from pathlib import Path
from struct import unpack_from
from time import sleep
from typing import List, Any, Callable, Union

# LOGGING
logging.basicConfig()
logger = logging.getLogger("ms4840")

# TODO
#    - read this from a config.ini
debugging = False

# only send debug level detail to the file
if debugging == True:
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler('/data/log/dbus-ms4840/debug.log')
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)
else:
    # everything else goes to 'current' except explict debug messages
    logger.setLevel(logging.INFO)
    shandler = logging.StreamHandler(stream = sys.stdout)
    shandler.setLevel(logging.INFO)
    logger.addHandler(shandler)

    fhandler = logging.FileHandler('/data/log/dbus-ms4840/debug.log')
    fhandler.setLevel(logging.DEBUG)
    logger.addHandler(fhandler)