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
debugging = False # use SIGUSR1 to override this

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

def get_venus_os_version() -> str:
    """
    Get the Venus OS version.

    :return: Venus OS version, e.g. v3.60
    """
    with open("/opt/victronenergy/version", "r") as f:
        return f.readline().strip()


def get_venus_os_image_type() -> str:
    """
    Get the Venus OS image type

    :return: Venus OS image type: normal or large
    """
    with open("/etc/venus/image-type", "r") as f:
        return f.readline().strip()


def get_venus_os_device_type() -> str:
    """
    Get the Venus OS device type.

    :return: Venus OS device type, e.g. Venus GX, Cerbo GX, etc.
    """
    with open("/sys/firmware/devicetree/base/model", "r") as f:
        return f.readline().strip()