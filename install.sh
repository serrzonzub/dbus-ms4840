#!/bin/bash

read -p "Install Epever Solarcharger on Venus OS at your own risk? [Y to proceed]" -n 1 -r
echo    # (optional) move to a new line
if [[ $REPLY =~ ^[Yy]$ ]]
then
	echo "Download and install pip3 and minimalmodbus"

	opkg update
	opkg install python3-pip
	pip3 install -U minimalmodbus


	echo "Download driver and library"

    data_dir="dbus-ms4840"
	cd /data

	#wget https://github.com/kassl-2007/dbus-ms4840/archive/master.zip
	#unzip master.zip
	#rm master.zip

	wget https://github.com/victronenergy/velib_python/archive/master.zip
	unzip master.zip
	rm master.zip

	mkdir -p ${dbus-ms4840}/ext/velib_python
	#cp -R dbus-ms4840-master/* dbus-ms4840
	cp -R velib_python-master/* ${dbus-ms4840}/ext/velib_python
	
	rm -r velib_python-master
	#rm -r dbus-ms4840-master

	echo "Add entries to serial-starter"
	cd ..
	sed -i '/service.*imt.*dbus-imt-si-rs485tc/a service ms4840		dbus-ms4840' /etc/venus/serial-starter.conf
	sed -i '$aACTION=="add", ENV{ID_BUS}=="usb", ENV{ID_MODEL}=="FT232R_USB_UART",          ENV{VE_SERVICE}="ms4840"' /etc/udev/rules.d/serial-starter.rules

	echo "Install driver"
	chmod +x /data/${data_dir}/driver/start-dbus-ms4840.sh
	chmod +x /data/${data_dir}/driver/dbus-ms4840.py
	chmod +x /data/${data_dir}/service/run
	chmod +x /data/${data_dir}/service/log/run

	ln -s /data/dbus-ms4840/driver /opt/victronenergy/dbus-ms4840
	ln -s /data/dbus-ms4840/service /opt/victronenergy/service-templates/dbus-ms4840

	echo "To finish, reboot the Venus OS device"
fi