this is for reading via minimodbus a helios ms4840 or bougerv mppt controller and adding it to the venus status webpage

this is a very basic version and i have no idea if i'm doing it all correctly.



left image is the port on the device; right is the RJ12 connect on the cable
![image](https://github.com/user-attachments/assets/52a5bc37-1c00-434b-8dbb-41885b793b71)


thanks to all the various people who came before me to help me understand and create a working version of this

- boguerv mppt controller: https://www.bougerv.com/products/40a-mppt-solar-charge-controller
- helios ms4840n mppt controller: https://www.helios-ne.com/products/mppt-solar-charge-controller-ms4830n-negative-grounded-model-touch-screen-operation.html

TODO:
- make it auto start (still working on the daemontool service setup)
  - right now i use `nohup python /data/dbus-ms4840/driver/dbus-ms4840.py /dev/ttyUSB1 &` or `screen python /data/dbus-ms4840/driver/dbus-ms4840.py /dev/ttyUSB1`
- retain battery Vmin/Vmax/Imax history (will store to local file) as the controller doesn't store this long term
