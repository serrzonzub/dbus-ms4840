#!/usr/bin/python

# dbus paths according to victron
# https://github.com/victronenergy/venus/wiki/dbus

# screen shots and mqtt -> dbus
# https://github.com/mr-manuel/venus-os_dbus-mqtt-solar-charger

# example used to create this
# https://github.com/kassl-2007/dbus-epever-tracer/blob/master/driver/dbus-epever-tracer.py

# to test
# /opt/victronenergy/serial-starter/stop-tty.sh ttyUSB1

# on my raspberry 3 it takes (quick observation, not emprical):
#    w/history   - DEBUG:root:spent 0.149287 in _update (max observed)
#    w/o history - DEBUG:root:spent 0.083079 in _update (max observed)


from asyncio import exceptions
import logging
import serial
import minimalmodbus
import time
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
import dbus
import dbus.service
import os
import sys
import platform
import argparse

# victron packages
sys.path.insert(
    1,
    os.path.join(
        os.path.dirname(__file__),
        "../ext/velib_python",
    ),
)
from vedbus import VeDbusService  # noqa: E402
from settingsdevice import (  # noqa: E402
    SettingsDevice,
)

# serial variables
baud_rate = 9600 # ms4840 doesn't speed any faster

# variables
debugging = False
softwareversion = '0.8'
serialnumber = '0000000000000000'
productname='ms4840'
hardwareversion = '00.00'
firmwareversion = '00.00'
connection = 'USB'
servicename = 'com.victronenergy.solarcharger.tty'
deviceinstance = 290    #VRM instanze
exceptionCounter = 0
#state = [0,5,3,6]
history_days = 10
total_trackers = 1

# formatting
def _a(p, v):
    return str("%.1f" % v) + "A"


def _n(p, v):
    return str("%i" % v)


def _s(p, v):
    return str("%s" % v)


def _v(p, v):
    return str("%.2f" % v) + "V"


def _w(p, v):
    return str("%i" % v) + "W"


def _kwh(p, v):
    return str("%i" % v) + "kWh"

def _C(p, v):
    return str("%i" % v) + "°C"

solar_charger_dict = {
    # general data
    "/NrOfTrackers": {"value": None, "textformat": _n},
    "/Pv/V": {"value": None, "textformat": _v},
    "/Pv/P": {"value": None, "textformat": _w},
    "/Pv/0/V": {"value": None, "textformat": _v},
    "/Pv/1/V": {"value": None, "textformat": _v},
    "/Pv/2/V": {"value": None, "textformat": _v},
    "/Pv/3/V": {"value": None, "textformat": _v},
    "/Pv/0/P": {"value": None, "textformat": _w},
    "/Pv/1/P": {"value": None, "textformat": _w},
    "/Pv/2/P": {"value": None, "textformat": _w},
    "/Pv/3/P": {"value": None, "textformat": _w},
    "/Yield/Power": {"value": None, "textformat": _w},
    # external control
    "/Link/NetworkMode": {"value": None, "textformat": _s},
    "/Link/BatteryCurrent": {"value": None, "textformat": _a},
    "/Link/ChargeCurrent": {"value": None, "textformat": _a},
    "/Link/ChargeVoltage": {"value": None, "textformat": _v},
    "/Link/NetworkStatus": {"value": None, "textformat": _s},
    "/Link/TemperatureSense": {"value": None, "textformat": _n},
    "/Link/TemperatureSenseActive": {"value": None, "textformat": _n},
    "/Link/VoltageSense": {"value": None, "textformat": _n},
    "/Link/VoltageSenseActive": {"value": None, "textformat": _n},
    # settings
    "/Settings/BmsPresent": {"value": None, "textformat": _n},
    "/Settings/ChargeCurrentLimit": {"value": None, "textformat": _n},
    # other paths
    "/Dc/0/Voltage": {"value": None, "textformat": _v},
    "/Dc/0/Current": {"value": None, "textformat": _a},
    "/Dc/0/Temperature": {"value": None, "textformat": _C},
    "/MppTemperature": {"value": None, "textformat": _C},
    "/Yield/User": {"value": None, "textformat": _kwh},
    "/Yield/System": {"value": None, "textformat": _kwh},
    "/Load/State": {"value": None, "textformat": _n},
    "/Load/I": {"value": None, "textformat": _a},
    "/ErrorCode": {"value": 0, "textformat": _n},
    "/State": {"value": 0, "textformat": _n},
    "/Mode": {"value": None, "textformat": _n},
    "/MppOperationMode": {"value": None, "textformat": _n},
    "/DeviceOffReason": {"value": None, "textformat": _s},
    "/Relay/0/State": {"value": None, "textformat": _n},
    # alarms
    "/Alarms/LowVoltage": {"value": None, "textformat": _n},
    "/Alarms/HighVoltage": {"value": None, "textformat": _n},
    # history
    "/History/Daily/0/Yield": {"value": None, "textformat": _kwh},
    "/History/Daily/0/MaxPower": {"value": None, "textformat": _w},
    "/History/Overall/DaysAvailable": {"value": history_days, "textformat": _n},
    "/History/Overall/MaxPvVoltage": {"value": None, "textformat": _n},
    "/History/Overall/MaxBatteryVoltage": {"value": None, "textformat": _n},
    "/History/Overall/MinBatteryVoltage": {"value": None, "textformat": _n},
    "/History/Overall/LastError1": {"value": None, "textformat": _n},
    "/History/Overall/LastError2": {"value": None, "textformat": _n},
    "/History/Overall/LastError3": {"value": None, "textformat": _n},
    "/History/Overall/LastError4": {"value": None, "textformat": _n},
}

# add in history paths to the dictionary
for day in range(history_days):
    solar_charger_dict.update(
        {
            "/History/Daily/" + str(day) + "/Yield": {"value": None, "textformat": _kwh},
            "/History/Daily/" + str(day) + "/MaxPower": {"value": None, "textformat": _kwh},
            "/History/Daily/" + str(day) + "/MinVoltage": {"value": None, "textformat": _v},
            "/History/Daily/" + str(day) + "/MaxVoltage": {"value": None, "textformat": _v}
        }
    )

if len(sys.argv) > 1:
    controller = minimalmodbus.Instrument(sys.argv[1], 1)
    servicename = 'com.victronenergy.solarcharger.' + sys.argv[1].split('/')[2]
else:
    print(f"no serial port given. bye.")
    sys.exit()

controller.serial.baudrate = baud_rate
controller.serial.bytesize = 8
controller.serial.parity = serial.PARITY_NONE
controller.serial.stopbits = 1
controller.serial.timeout = 0.2
controller.mode = minimalmodbus.MODE_RTU
controller.clear_buffers_before_each_transaction = True
#controller.close_port_afer_each_call = True

print(__file__ + " is starting up, use -h argument to see optional arguments")

class MS4840(object):
    def __init__(self, paths):
        self._dbusservice = VeDbusService(servicename, register=False)
        self._paths = paths

        # path conversion functions
        _kwh = lambda p, v: (str("%i" % v) + 'kWh')
        _a = lambda p, v: (str("%.1f" % v) + 'A')
        _w = lambda p, v: (str("%.1f" % v) + 'W')
        _v = lambda p, v: (str("%.2f" % v) + 'V')
        _c = lambda p, v: (str(v) + '°C')
        _n = lambda p, v: (str("%i" % v))
        _s = lambda p, v: (str("%s" % v))

        self.got_history = False
        self.solar_controller = {}
        self.solar_controller_history = {}
        self.pdu_addresses = {\
            "sver": {"reg": 20, "len": 8}, # 0x0014h\
            "hver": {"reg": 21, "len": 8}, # 0x0015h\
            "system information": {"reg": 12, "len": 8}, # 0x000Ch\
            
            "load_status": {"reg": 269, "len": 1}, # 0x010Dh\
            "current_system_voltage": {"reg": 256, "len": 1}, # 0x0100h\
            "battery_power": {"reg": 257, "len": 1}, # 0x0101h\
            "battery_voltage": {"reg": 258, "len": 1}, # 0x0102h\
            "solar_current": {"reg": 259, "len": 1}, # 0x0103h\ - amps
            "solar_power": {"reg": 260, "len": 1}, # 0x0104h\ - watts
            "temperatures": {"reg": 261, "len": 1}, # 0x0105h\
            "solar_voltage": {"reg": 265, "len": 1}, # 0x0109h \
            "max_power_day": {"reg": 266, "len": 1}, # 0x010Ah
            "power_gen_day": {"reg": 267, "len": 1}, # 0x010Bh
            "battery_type": {"reg": 515, "len": 1}, # 0x0202h \
            "uptime": {"reg": 271, "len": 1}, # 0x010fh
            "total_power_generation": {"reg": 272, "len": 2}, # 0x0110-0x0111h, also total yield?
            "0dhist": {"reg": 1024, "len": 5}, # 0x0400h \
            "1dhist": {"reg": 1025, "len": 5} # 0x0400h \
        }

        # create the history pdu_address entries
        for day in range(history_days):
            pdu_name = str(day) + "hist"
            reg = (1024 + int(day))
            self.pdu_addresses.update(
            {
                pdu_name: {"reg": reg, "len": 5},
            })

        logging.debug("%s /DeviceInstance = %d" % (servicename, deviceinstance))

        # Create the management objects, as specified in the ccgx dbus-api document
        self._dbusservice.add_path('/Mgmt/ProcessName', __file__)
        self._dbusservice.add_path('/Mgmt/ProcessVersion', softwareversion)
        self._dbusservice.add_path('/Mgmt/Connection', connection)

        # Create the mandatory objects
        self._dbusservice.add_path('/DeviceInstance', deviceinstance)
        self._dbusservice.add_path('/ProductId', 1)
        self._dbusservice.add_path('/ProductName', productname)
        self._dbusservice.add_path('/FirmwareVersion', firmwareversion)
        self._dbusservice.add_path('/HardwareVersion', hardwareversion)
        self._dbusservice.add_path('/Connected', 1)
        self._dbusservice.add_path('/Serial', serialnumber)
        self._dbusservice.add_path('/CustomName', None, writeable=True)

        for path, settings in self._paths.items():
            self._dbusservice.add_path(
                path,
                settings["value"],
                gettextcallback=settings["textformat"],
                writeable=True,
                onchangecallback=self._handlechangedvalue,
            )

        # register VeDbusService after all paths where added
        self._dbusservice.register()

        self._dbusservice['/NrOfTrackers'] = total_trackers

        # create the dictionary holding read values
        #for pdu_address in self.pdu_addresses:
        #    pdu_name = pdu_address
        #    self.solar_controller[pdu_name] = [0]
        #print(self.solar_controller)

        def _get_solar_charger_history(self, days):
            if self.got_history == False:
                days = (self.solar_controller["uptime"][0] - 1)

            if days > history_days:
                days = (history_days - 1)

            for day in range(days):
                # variable name in solar_controller
                value_key = str(day) + "hist"
                yield_key = "/History/Daily/" + str(day) + "/Yield"
                maxpower_key = "/History/Daily/" + str(day) + "/MaxPower"
                reg = int(1024 + day)
                print(f"trying to get day {day} of {days} of history (reg: {reg})")
                self.solar_controller_history[day] = controller.read_registers(reg, 5, 3)
                self.dbusservice[yield_key] = (self.solar_controller[value_key][0] / 1000)
                self.dbusservice[maxpower_key] = (self.solar_controller[value_key][2])

            print(self.solar_controller_history)
            self.got_history = True

        # register the update function for the dbus paths
        GLib.timeout_add(1000, self._update)

    def _handlechangedvalue(self, path, value):
        logging.debug("someone else updated %s to %s" % (path, value))
        return True  # accept the change
    
    def _update(self):
        global exceptionCounter
        start_time = time.process_time()

        # translate the ms4840 mptt state to victron's state
        def _calculate_state(status, s_curr, b_volt):
            if status == 0: # we are off, due to darkness?
                return 0 # off
            elif status == 2: # mppt reports mptt
                # calculate which mode we are in based on solar current (amps)?
                if s_curr > 10:
                    return 3 # bulk
                elif s_curr > 3 and s_curr < 10:
                    return 4 # absorption
                elif s_curr < 3:
                    return 5 # float
                return 3 # mppt tracker active
            elif status == 3: # mppt reports equalizing
                return 7 # equalize
            elif status == 4: # mppt reports boost
                return 3 # boost and bulk are the same?
            elif status == 5: # mptt reports float
                return 5 # float
            elif status == 6: # mpttp reports current ower power or over temperature
                return 2 # fault
            else:
                return 3 # default to equalizing charge?

        # go get the data from the solar controller (mppt)
        try:
            for pdu_address in self.pdu_addresses:
                pdu_name = pdu_address
                reg = self.pdu_addresses[pdu_address]['reg']
                reg_len = self.pdu_addresses[pdu_address]['len']

                # only get the history records every 30 seconds to reduce traffic since they won't change as fast
                index = self._dbusservice["/UpdateIndex"]                
                if (index % 30) != 0 and "hist" in pdu_name:
                    continue
                
                #print(f"trying to read reg: {reg} - name: {pdu_name}")
                pdu_value = controller.read_registers(reg, reg_len, 3)
                self.solar_controller[pdu_name] = pdu_value
        # communications error...
        except IOError as e:
            print(f"read_register failed")
            print(e)
        # everything else error...
        except:
            print(exceptions)
            exceptionCounter +=1
            if exceptionCounter  >= 3:
                #print(f"sleeping for 3")
                exceptionCounter = 0
                time.sleep(3)
        # all seems to have gone well, let's process the data
        else:
            #print(self.solar_controller)
            self._dbusservice['/Dc/0/Voltage'] = (self.solar_controller["battery_voltage"][0] / 10 )
            self._dbusservice['/Dc/0/Current'] = (self.solar_controller["solar_current"][0] * 0.01)
            self._dbusservice['/Dc/0/Temperature'] = (self.solar_controller["temperatures"][0] >> 0 & 0xff) # <-- lower 8 bits
            self._dbusservice['/MppTemperature'] = (self.solar_controller["temperatures"][0] >> 8 & 0xff) # <-- lower 8 bits
            # t2 = value >> 8 & 0xff < --> upper 8 bits
            self._dbusservice['/Pv/V'] = (self.solar_controller["solar_voltage"][0] / 10)
            self._dbusservice['/Pv/P'] = (self.solar_controller["solar_power"][0])
            self._dbusservice['/Yield/Power'] = (self.solar_controller["solar_power"][0])

            # i don't have a load option on the bougerv ms4840/helios ms4840 mppt controller
            self._dbusservice['/Load/State'] = 0
            #self._dbusservice['/Load/I'] = c3100[13]/100

            self._dbusservice['/History/Overall/DaysAvailable'] = (self.solar_controller["uptime"][0])
            self._dbusservice['/History/Daily/0/Yield'] = (self.solar_controller["power_gen_day"][0] / 1000)
            self._dbusservice['/History/Daily/0/MaxPower'] = (self.solar_controller["max_power_day"][0])
            # state is the current method the battery is being charged (bulk, absortion, float)
            
            state = _calculate_state(self.solar_controller["load_status"][0],\
                                     self.solar_controller["solar_current"][0] * 0.01,\
                                     self.solar_controller["battery_voltage"][0] / 10)
                #load_status[0], (solar_current[0] * 0.01), (battery_voltage[0] / 10 ))
            #print(f"state={state}")
            self._dbusservice['/State'] = state

            #for day in range(int(self.solar_controller["uptime"][0])):
            # it costs us very little to update the same variables in memory (this isn't low latency programming)
            for day in range(int(history_days)):
                history_key = str(day) + "hist"
                #max_power_key = str(day) + "hist_max_power"
                #max_voltage_key = str(day) + "hist_max_voltage"
                #max_voltage_key = str(day) + "hist_min_voltage"
                #reg = int(1024 + day)
                #print(f"trying to get day {day} of {days} of history (reg: {reg})")
                #self.solar_controller_history[day] = controller.read_registers(reg, 5, 3)
                self._dbusservice[f"/History/Daily/{day}/Yield"] = (self.solar_controller[history_key][0] / 1000)
                self._dbusservice[f"/History/Daily/{day}/MaxPower"] = (self.solar_controller[history_key][2])
                self._dbusservice[f"/History/Daily/{day}/MaxVoltage"] = (self.solar_controller[history_key][3])
                self._dbusservice[f"/History/Daily/{day}/MinVoltage"] = (self.solar_controller[history_key][4])

            # if we have a new maximum yield power, reflect it today (probably redundant)
            if self._dbusservice['/Yield/Power'] > self._dbusservice['/History/Daily/0/MaxPower']:
                self._dbusservice['/History/Daily/0/MaxPower'] = self._dbusservice['/Yield/Power']

            # total power generation all time in WH
            self._dbusservice['/Yield/System'] = (self.solar_controller['total_power_generation'][1])

        # increment UpdateIndex - to show that new data is available
        index = self._dbusservice["/UpdateIndex"] + 1  # increment index
        if index > 255:  # maximum value of the index
            index = 0  # overflow from 255 to 0
        self._dbusservice["/UpdateIndex"] = index
        
        
        # calculate the elapsed time if debugging is enabled
        if debugging == True:
            elapsed_time = (time.process_time() - start_time)
            logging.debug("spent %f in _update" % (elapsed_time))

        # and we're done
        return True

def main():
    if debugging == True:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    from dbus.mainloop.glib import DBusGMainLoop
    # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
    DBusGMainLoop(set_as_default=True)

    # add to the dbus paths
    paths_dbus = {
        "/UpdateIndex": {"value": 0, "textformat": _n},
    }
    solar_charger_dict.update(paths_dbus)

    # create the object
    ms4840 = MS4840(paths = solar_charger_dict)

    # and off to the races we go
    logging.info('Connected to dbus, and switching over to GLib.MainLoop() (= event based)')
    mainloop = GLib.MainLoop()
    mainloop.run()


if __name__ == "__main__":
    main()
