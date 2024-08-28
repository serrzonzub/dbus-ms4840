#!/bin/bash

# remove comment for easier troubleshooting
#set -x

# copy the service "templates" into /service and make them executable
cp -rf /data/dbus-ms4840/service /service/dbus-ms4840
chmod +x /service/dbus-ms4840/run
chmod +x /service/dbus-ms4840/log/run
