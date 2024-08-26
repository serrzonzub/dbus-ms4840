this is for reading via minimodbus a helios ms4840 or bougerv mppt controller and adding it to the venus status webpage

this is a very basic version and i have no idea if i'm doing it all correctly.

thanks to all the various people who came before me to help me understand and create a working version of othis

TODO:
- make it auto start (still working on the daemontool service setup)
  - right now i use `nohup python /data/dbus-ms4840/driver/dbus-ms4840.py /dev/ttyUSB1 &`

