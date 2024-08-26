this is for reading via minimodbus a helios ms4840 or bougerv mppt controller and adding it to the venus status webpage

this is a very basic version and i have no idea if i'm doing it all correctly.

rs485 cable pin-out:
| pin | used for |
| --- | ---------|
| pin 1 | vdd (3.3v) |
| pin 2 | vdd (3.3v) |
| pin 3 | gnd | 
| pin 4 | gnd |
| ping 5 | D- |
| ping 6 | D+ |

thanks to all the various people who came before me to help me understand and create a working version of this

- boguerv mppt controller: https://www.bougerv.com/products/40a-mppt-solar-charge-controller
- helios ms4840n mppt controller: https://www.helios-ne.com/products/mppt-solar-charge-controller-ms4830n-negative-grounded-model-touch-screen-operation.html

TODO:
- make it auto start (still working on the daemontool service setup)
  - right now i use `nohup python /data/dbus-ms4840/driver/dbus-ms4840.py /dev/ttyUSB1 &` or `screen python /data/dbus-ms4840/driver/dbus-ms4840.py /dev/ttyUSB1`
- retain battery Vmin/Vmax/Imax history (will store to local file) as the controller doesn't store this long term