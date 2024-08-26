#!/bin/bash

read -p "Install MS4840N Solarcharger on Venus OS at your own risk? [Y to proceed]" -n 1 -r
echo    # (optional) move to a new line
if [[ $REPLY =~ ^[Yy]$ ]]
then
	# we need python3-pip and minimalmodbus
    echo "Download and install pip3 and minimalmodbus"
    opkg update
    opkg install python3-pip
    pip3 install -U minimalmodbus


    echo "Download driver and library"

	# into which directory do we want the driver?
    data_dir="dbus-ms4840"
    cd /data

    # download and unzip the code
    wget https://github.com/serrzonzub/dbus-ms4840/archive/refs/heads/main.zip
    unzip main.zip
    rm main.zip

    # velib is required, download and unzip
    wget https://github.com/victronenergy/velib_python/archive/master.zip
    unzip master.zip
    rm master.zip

    mkdir -p ${dbus-ms4840}/ext/velib_python
    cp -R dbus-ms4840-main/* dbus-ms4840
    cp -R velib_python-master/* ${dbus-ms4840}/ext/velib_python
    
	# remove the temporary directories from the unzipping
    rm -r velib_python-master
    rm -r dbus-ms4840-main

	# this is to autostart correctly
	#    (20240826 - this doesn't work yet)
    echo "Add entries to serial-starter"
    cd ..
    #sed -i '/service.*imt.*dbus-imt-si-rs485tc/a service ms4840        dbus-ms4840' /etc/venus/serial-starter.conf
    #sed -i '$aACTION=="add", ENV{ID_BUS}=="usb", ENV{ID_MODEL}=="FT232R_USB_UART",          ENV{VE_SERVICE}="ms4840"' /etc/udev/rules.d/serial-starter.rules

    echo "Install driver"
    chmod +x /data/${data_dir}/driver/start-dbus-ms4840.sh
    chmod +x /data/${data_dir}/driver/dbus-ms4840.py
    chmod +x /data/${data_dir}/service/run
    chmod +x /data/${data_dir}/service/log/run

    ln -s /data/${data_dir}/driver /opt/victronenergy/${data_dir}
    ln -s /data/${data_dir}/service /opt/victronenergy/service-templates/${data_dir}
    echo "To finish, reboot the Venus OS device"
fi
