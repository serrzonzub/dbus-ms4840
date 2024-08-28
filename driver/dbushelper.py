import sys
import os
import platform
import dbus
from time import sleep, time
from utils import logger
from xml.etree import ElementTree
import requests
import threading

class DbusHelper:
    def __init__(self, solarcontroller, servicename):
        self.solarcontroller = solarcontroller
        self.instance = 1
        self._dbusname = servicename

    def create_pid_file(self) -> None:
        """
        Create a pid file for the driver with the device instance as file name suffix.
        Keep the file locked for the entire script runtime, to prevent another instance from running with
        the same device instance. This is achieved by maintaining a reference to the "pid_file" object for
        the entire script runtime storing "pid_file" as an instance variable "self.pid_file".
        """
        # only used for this function
        import fcntl

        # path to the PID file
        pid_file_path = f"/var/tmp/dbus-ms4840_{self.instance}.pid"

        try:
            # open file in append mode to not flush content, if the file is locked
            self.pid_file = open(pid_file_path, "a")

            # try to lock the file
            fcntl.flock(self.pid_file, fcntl.LOCK_EX | fcntl.LOCK_NB)

        # fail, if the file is already locked
        except OSError:
            logger.error(
                "** DRIVER STOPPED! Another battery with the same serial number/unique identifier "
                + f'"{self.battery.unique_identifier()}" found! **'
            )
            logger.error("Please check that the batteries have unique identifiers.")

            self.pid_file.close()
            sleep(60)
            sys.exit(1)

        # Seek to the beginning of the file
        self.pid_file.seek(0)
        # Truncate the file to 0 bytes
        self.pid_file.truncate()
        # Write content to file
        self.pid_file.write(f"{self._dbusname}:{os.getpid()}\n")
        # Flush the file buffer
        self.pid_file.flush()

        # Ensure the changes are written to the disk
        # os.fsync(self.pid_file.fileno())

        logger.info(f"PID ({os.getpid()}) file created successfully: {pid_file_path}")