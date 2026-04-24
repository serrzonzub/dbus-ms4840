#!/usr/bin/python

# this driver is (mostly) meant to record and report data, it isn't meant to controller your system
# use at your own risk

# dbus paths according to victron
# https://github.com/victronenergy/venus/wiki/dbus

# screen shots and mqtt -> dbus
# https://github.com/mr-manuel/venus-os_dbus-mqtt-solar-charger

# example projects used to create this "masterpiece"
# https://github.com/kassl-2007/dbus-epever-tracer/blob/master/driver/dbus-epever-tracer.py
# https://github.com/rosswarren/epevermodbus/blob/main/epevermodbus/driver.py
# https://github.com/mr-manuel/venus-os_dbus-mqtt-solar-charger/blob/master/dbus-mqtt-solar-charger/dbus-mqtt-solar-charger.py

# to test
# /opt/victronenergy/serial-starter/stop-tty.sh ttyUSB1

# on my raspberry 3 it takes (quick observation, not emprical):
#    w/history   - DEBUG:root:spent 0.149287 in _update (max observed)
#    w/o history - DEBUG:root:spent 0.083079 in _update (max observed)

import pprint
from asyncio import exceptions
import serial
import minimalmodbus
import time
import datetime
import logging
import dbus
from dbus.mainloop.glib import DBusGMainLoop
from dbus.exceptions import (DBusException, UnknownMethodException)
from gi.repository import GLib
import os
import signal
import sys
import platform
import argparse
from dbushelper import DbusHelper
from utils import (logger, debugging,
    get_venus_os_version,
    get_venus_os_image_type,
    get_venus_os_device_type,
)

# victron packages
sys.path.insert(
    1,
    os.path.join(
        os.path.dirname(__file__),
        "../ext/velib_python",
    ),
)
from vedbus import VeDbusService  # noqa: E402
from ve_utils import get_vrm_portal_id  # noqa: E402
from settingsdevice import (  # noqa: E402
    SettingsDevice,
)

# serial variables (we probably want this from a config file at some point)
baud_rate = 9600 # ms4840 doesn't speed any faster
controller_address = 1 # the andress of the controller

# general variables
softwareversion = '0.9.4 (20260424)'
serialnumber = '0000000000000000'
productname='ms4840'
hardwareversion = '00.00'
firmwareversion = '00.00'
connection = 'USB'
servicename = 'com.victronenergy.solarcharger.tty'
deviceinstance = 290    # VRM instanze
exceptionCounter = 0
history_days = 31 # number of days to get history for, if available
total_trackers = 1 # number of mppt devices

# formatting
def _a(p, v): # amps
    return str("%.1f" % v) + "A"

def _n(p, v): # number
    return str("%i" % v)

def _s(p, v): # string
    return str("%s" % v)

def _v(p, v): # voltage
    return str("%.2f" % v) + "V"

def _w(p, v): # watts
    return str("%i" % v) + "W"

def _kwh(p, v): # kilowatt hours
    return str("%i" % v) + "kWh"

def _wh(p, v): # watt hours
    return str("%i" % v) + "Wh"

def _C(p, v): # celcius
    return str("%i" % v) + "°C"

# dictionary for various solar charger valeus
solar_charger_dict = {
    # general data
    "/NrOfTrackers": {"value": None, "textformat": _n},
    "/Pv/V": {"value": None, "textformat": _v},
    "/Pv/P": {"value": None, "textformat": _w},
    "/Pv/Name": {"value": None, "textformat": _s},
    "/Yield/Power": {"value": None, "textformat": _w},
    "/Yield/User": {"value": None, "textformat": _wh},
    "/Yield/System": {"value": None, "textformat": _wh},

    # if you have more than one mppt controller...
    #"/Pv/0/V": {"value": None, "textformat": _v},
    #"/Pv/1/V": {"value": None, "textformat": _v},
    #"/Pv/2/V": {"value": None, "textformat": _v},
    #"/Pv/3/V": {"value": None, "textformat": _v},
    #"/Pv/0/P": {"value": None, "textformat": _w},
    #"/Pv/1/P": {"value": None, "textformat": _w},
    #"/Pv/2/P": {"value": None, "textformat": _w},
    #"/Pv/3/P": {"value": None, "textformat": _w},

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
    # the ms4840-n doesn't have capability to offer load
    "/Load/State": {"value": None, "textformat": _n},
    "/Load/I": {"value": None, "textformat": _a},
    # errors/state/operating mode/relay
    "/ErrorCode": {"value": 0, "textformat": _n},
    "/State": {"value": 0, "textformat": _n},
    "/Mode": {"value": None, "textformat": _n},
    "/MppOperationMode": {"value": None, "textformat": _n},
    "/DeviceOffReason": {"value": None, "textformat": _s},
    "/Relay/0/State": {"value": None, "textformat": _n},
    # alarms
    "/Alarms/LowVoltage": {"value": None, "textformat": _n},
    "/Alarms/HighVoltage": {"value": None, "textformat": _n},
    "/Alarms/HighTemperature": {"value": None, "textformat": _n},
    "/Alarms/ShortCircuit": {"value": None, "textformat": _n},
    # history (daily is created dynamically below)
    "/History/Overall/DaysAvailable": {"value": history_days, "textformat": _n},
    "/History/Overall/MaxPvVoltage": {"value": 0.0, "textformat": _v},
    "/History/Overall/MaxBatteryVoltage": {"value": 0, "textformat": _v},
    "/History/Overall/MinBatteryVoltage": {"value": 0, "textformat": _v},
    "/History/Overall/LastError1": {"value": None, "textformat": _n},
    "/History/Overall/LastError2": {"value": None, "textformat": _n},
    "/History/Overall/LastError3": {"value": None, "textformat": _n},
    "/History/Overall/LastError4": {"value": None, "textformat": _n},
}

# add in history paths to the dictionary
for day in range(history_days):
    # convert day to a string once
    s_day = str(day)

    solar_charger_dict.update(
        {
            "/History/Daily/" + s_day + "/Yield": {"value": 0, "textformat": _wh},
            "/History/Daily/" + s_day + "/MaxPower": {"value": 0, "textformat": _kwh},
            "/History/Daily/" + s_day + "/MinVoltage": {"value": 0, "textformat": _v},
            # this isn't used?
            #"/History/Daily/" + s_day + "/MaxVoltage": {"value": None, "textformat": _v},
            "/History/Daily/" + s_day + "/MaxPvVoltage": {"value": 0, "textformat": _v},
            "/History/Daily/" + s_day + "/MinBatteryVoltage": {"value": 0, "textformat": _v},
            "/History/Daily/" + s_day + "/MaxBatteryVoltage": {"value": 0, "textformat": _v},
            "/History/Daily/" + s_day + "/MaxBatteryCurrent": {"value": 0, "textformat": _a},

            # for recording duration of different charge states
            "/History/Daily/" + s_day + "/TimeInBulk": {"value": 0, "textformat": _n},
            "/History/Daily/" + s_day + "/TimeInAbsorption": {"value": 0, "textformat": _n},
            "/History/Daily/" + s_day + "/TimeInFloat": {"value": 0, "textformat": _n},
        }
    )

# we need to know what serialport / usb to connect to and we expect that from the command line
#   as argument 1.
if len(sys.argv) > 1:
    controller_path = sys.argv[1] # /dev/ttyUSB1
    controller_suffix = sys.argv[1].split('/')[2] # ttyUSB
    controller = minimalmodbus.Instrument(controller_path, controller_address)
    servicename = 'com.victronenergy.solarcharger.' + controller_suffix
else:
    logger.info(f"no port given. bye.")
    sys.exit()

controller.serial.baudrate = baud_rate
controller.serial.bytesize = 8
controller.serial.parity = serial.PARITY_NONE
controller.serial.stopbits = 1
controller.serial.timeout = 0.2
controller.mode = minimalmodbus.MODE_RTU
controller.clear_buffers_before_each_transaction = True
#controller.close_port_afer_each_call = True

logger.info("")
logger.info("Starting dbus-ms4840")

class MS4840(object):
    def __init__(self, paths):
        logger.info(f"trying to register '{servicename}' on the dbus")
        res = self._dbusservice = VeDbusService(servicename, register=False)

        self.debugging = debugging
        self._paths = paths
        self.got_history = False
        self.loop_index = 0
        self.solar_controller = {}
        self.solar_controller_history = {}
        self.solar_controller_chargetime = {
            "bulk": 0, # total bulk charge time
            "abs": 0, # total absorbtion charge time
            "float": 0 # total float charge time
        }

        # "len" is word length, 1word=2bytes, 2words=4bytes, 5words=10bytes
        self.pdu_addresses = {\
            "sver": {"reg": 20, "len": 1}, # 0x0014h
            "hver": {"reg": 21, "len": 1}, # 0x0015h
            "system_info": {"reg": 12, "len": 8}, # 0x000Ch

            # annex 6
            #    0-no charge, 1-open charge, 2-mppt charge
            #    3-equializing charge, 4-boost charge, 5-float charge
            #    6-current limit (over power or over temp)
            "load_status": {"reg": 269, "len": 1}, # 0x010Dh
            "current_system_voltage": {"reg": 256, "len": 1}, # 0x0100h
            "battery_power": {"reg": 257, "len": 1}, # 0x0101h
            "battery_voltage": {"reg": 258, "len": 1}, # 0x0102h
            "solar_current": {"reg": 259, "len": 1}, # 0x0103h - charging current flowing into the battery in amps
            "solar_power": {"reg": 260, "len": 1}, # 0x0104h - doc says amps, but i think it's watts
            "temperatures": {"reg": 261, "len": 1}, # 0x0105h
            "solar_voltage": {"reg": 265, "len": 1}, # 0x0109h
            "max_power_day": {"reg": 266, "len": 1}, # 0x010Ah
            "power_gen_day": {"reg": 267, "len": 1}, # 0x010Bh
            "elec_consumption_day": {"reg": 268, "len": 1}, # 0x010Ch, in WH
            "alarm_info": {"reg": 270, "len": 1}, # 0x010Eh
            #"system_voltage": {"reg": 515, "len": 1}, # 0x0202h - 12/24/36/48/FF(auto)
            "battery_type": {"reg": 516, "len": 1}, # 0x0203h - 0-3 (flood, sealed, gel, li)
            "uptime": {"reg": 271, "len": 1}, # 0x010fh
            "total_power_generation": {"reg": 272, "len": 3}, # 0x0110-0x0111h, also total yield?
            "total_power_consumption": {"reg": 274, "len": 3}, # 0x112-0x113h
            "0dhist": {"reg": 1024, "len": 5}, # 0x0400h
            "1dhist": {"reg": 1025, "len": 5} # 0x0400h
        }

        # create the history pdu_address entries
        for day in range(history_days):
            pdu_name = str(day) + "hist"
            reg = (1024 + int(day))
            self.pdu_addresses.update(
            {
                pdu_name: {"reg": reg, "len": 5},
            })

        logger.debug("%s /DeviceInstance = %d" % (servicename, deviceinstance))

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
        self._dbusservice.add_path('/CustomName', '', writeable=True)

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

        # setup default values for various paths
        self._dbusservice['/NrOfTrackers'] = total_trackers
        self._dbusservice['/Load/State'] = 0 # on the ms4840n this is always 0 since there is no load capability
        self._dbusservice['/Load/I'] = 0 # on the ms4840n this is always 0 since there is no load capability

        # register the update function for the dbus paths every second
        GLib.timeout_add(1000, self._update)

    # used to update values from the mppt controller on boot
    def _update_on_boot(self):
        pass

    def _handlechangedvalue(self, path, value):
        logger.debug("someone else updated %s to %s" % (path, value))
        return True  # accept the change

    # if we need to update the history do it here
    def _update_history(self, h = 0, m = 0, s = 0):
        # move the history pv values from day X to day X-1
        for day in range(int(history_days)):
            if day <= 0: # skip today
                continue
            prev_day = (day - 1)
            
            # update the local list with the new values
            history_key = str(prev_day) + "hist"
            self._dbusservice[f"/History/Daily/{day}/Yield"] = (self.solar_controller[history_key][0] / 1000) # labeled as kWh in GUI, ms4840 reports WH
            self._dbusservice[f"/History/Daily/{day}/MaxPower"] = self.solar_controller[history_key][2]
            self._dbusservice[f"/History/Daily/{day}/MaxBatteryVoltage"] = (self.solar_controller[history_key][3] / 10)
            self._dbusservice[f"/History/Daily/{day}/MinBatteryVoltage"] = (self.solar_controller[history_key][4] / 10)
            
            # and these values are only stored on the mptt - day0 is set as part of _update
            self._dbusservice[f'/History/Daily/{day}/MaxPvVoltage'] = self._dbusservice[f'/History/Daily/{prev_day}/MaxPvVoltage']
            self._dbusservice[f'/History/Daily/{day}/MaxBatteryCurrent'] = self._dbusservice[f'/History/Daily/{prev_day}/MaxBatteryCurrent']
        logger.info(f'midnight - updating history@{h}:{m}:{s}, uptime: {self.solar_controller["uptime"][0]}')
    
    # this is where the bulk of the work is done to read values and update the data
    def _update(self):
        global exceptionCounter
        # update my debugging based on global debugging (signal triggered change)
        self.debugging = debugging
        start_time = time.process_time()

        def _convert_to_string(data):
            # data = [8224, 19795, 11572, 14388, 12366, 8224, 8224, 8224] "  MS-4840N   "
            res = ''
            for byte in data:
                b1 = (byte >> 8 & 0xff) # 2 MSBs
                b2 = (byte & 0xff) # 2 LSBs
                res = res + chr(b1) + chr(b2)

            # return it the stripped string ("MS-4840N")
            return res.strip()

        # translate the ms4840 mptt state to victron's state (i think/hope)
        #    - not sure the s_curr values reflect true state, i'm sure it's more complicated
        def _calculate_state(status: int, s_curr, b_volt):
            # based on doc, high 8 bytes are load status, low 8 bytes are charging status
            load_status = (status >> 8 & 0xff) # high byte
            charging_status = (status & 0xff) # low byte

            if debugging == True:
                logger.debug(f'status word={status} (low={charging_status}, high={load_status}), current={s_curr}, battvolt={b_volt}')

            if charging_status == 0: # we are off, due to darkness?
                return 0 # off
            elif charging_status == 1: # open charge mode
                return 2 # fault, although this isn't quite accurate
            elif charging_status == 2: # mppt reports mptt
                # calculate which mode we are in based on solar current (amps)?
                if s_curr > 10:
                    return 3 # bulk
                elif s_curr > 3 and s_curr < 10:
                    return 4 # absorption
                elif s_curr < 3:
                    return 5 # float
                return 3 # mppt tracker active
            elif charging_status == 3: # mppt reports equalizing
                return 7 # equalize
            elif charging_status == 4: # mppt reports boost
                return 3 # boost and bulk are the same?
            elif charging_status == 5: # mptt reports float
                return 5 # float
            elif charging_status == 6: # mpttp reports current over power or over temperature
                return 2 # fault
            else: # shouldn't get here
                return 3 # default to equalizing charge?

        def _calculate_midnight():
            # we need to store today's values in the history for the next day
            # get the current time
            now = datetime.datetime.now()
            # calculate the time until midnight
            midnight = datetime.datetime(now.year, now.month, now.day) + datetime.timedelta(days=1)
            time_until_midnight = midnight - now
            # extract hours and minutes
            hours, seconds = divmod(time_until_midnight.seconds, 3600)
            minutes = seconds // 60

            return hours, minutes, seconds
        
        def _get_errorcode(error_code: int) -> int:
            # default to no error
            return_error_code = 0

            if error_code == 0: # no error
                return_error_code = 0 # no error
            elif error_code == 1: # battery over discharged
                logger.info("battery is over discharged")
                return_error_code = 0 # no error - victron doens't have this error
            elif error_code == 2: # battery over voltage
                logger.info("battery voltage is low")
                return_error_code = 2 # battery voltage too high
            elif error_code == 3: # load short circuit
                logger.info("load short circuit - check rs484/temp cables")
                return_error_code = 8 # battery voltage sense disconnected
            elif error_code == 4: # load power too big or load open circuit
                logger.info("load power too big or load open circuit")
                return_error_code = 18 # controller over-current
            elif error_code == 5: # controller temperature too high
                logger.info("solar controller temerature is too high")
                return_error_code = 22 # controller over-current
            elif error_code == 6: # surrounding temperature too high
                logger.info("surrounding temperature is too high")
                return_error_code = 1 # battery temperature too high
            elif error_code == 7: # input power too big (too high)
                logger.info("input power too big")
                return_error_code = 35 # pv over-power
            elif error_code == 8: # input side short circuit
                logger.info("input side short circuit")
                return_error_code = 27 # charger short circuit
            elif error_code == 9: # solar panel input over voltage
                logger.info(f"solar panel input is over voltage {self._dbusservice['/Pv/V']}")
                return_error_code = 33
            elif error_code == 12: # solar panel reverse connectivity ('doh!)
                logger.info("solar panel polarity is reversed")
                return_error_code = 27 # charger short circuit
            elif error_code == 13: # battery reverse connectivity ('doh!)
                logger.info("battery polarity is reversed")
                return_error_code = 27 # charger short circuit
            else: # ignore everything else and or set to 0
                return_error_code = 0 # 
            
            return return_error_code


        # go get the data from the solar controller (mppt)
        #    everything returns as a list
        try:
            for pdu_address in self.pdu_addresses:
                pdu_name = pdu_address
                reg = self.pdu_addresses[pdu_address]['reg']
                reg_len = self.pdu_addresses[pdu_address]['len']

                # only process certain paths on loop_index 0 to save communication time
                # TODO
                #    - really only get this on startup
                if self.loop_index != 0 and "ver" in pdu_name:
                    continue
                if self.loop_index != 0 and "system_info" in pdu_name:
                    continue

                # only get these records every X interval to reduce serial
                #    traffic since they won't change fast if at all
                if ((self.loop_index % 60) != 0) and "hist" in pdu_name:
                    continue
                elif ((self.loop_index % 90) != 0) and "ver" in pdu_name:
                    continue
                elif ((self.loop_index % 90) != 0) and "system_info" in pdu_name:
                    continue

                if debugging:
                    logger.debug(f"trying read_register (name={pdu_name}, reg={reg}, reg_len={reg_len})")
                pdu_value = controller.read_registers(reg, reg_len, 3)
                self.solar_controller[pdu_name] = pdu_value
        # communications error...
        except IOError as e:
            logger.info(f"error={e}")
            logger.info(f"read_register (name={pdu_name}, reg={reg}, reg_len={reg_len}) failed")
        # everything else error...
        except:
            logger.info(f"exception={exceptions}")
            logger.info(f"read_register (name={pdu_name}, reg={reg}, reg_len={reg_len}) failed")
            exceptionCounter +=1
            if exceptionCounter  >= 3:
                #print(f"sleeping for 3")
                exceptionCounter = 0
                time.sleep(3) # only sleeps when we've had three exceptions in a row
        # all seems to have gone well, let's process the data
        else:
            exceptionCounter = 0
            self._dbusservice['/ProductName'] = _convert_to_string(self.solar_controller['system_info'])
            # these are just converted to integers and divided by 100 (for now)
            self._dbusservice['/FirmwareVersion'] = (self.solar_controller['sver'][0] / 100)
            self._dbusservice['/HardwareVersion'] = (self.solar_controller['hver'][0] / 100)

            self._dbusservice['/Dc/0/Voltage'] = (self.solar_controller["battery_voltage"][0] / 10 )
            self._dbusservice['/Dc/0/Current'] = (self.solar_controller["solar_current"][0] * 0.01)
            self._dbusservice['/Dc/0/Temperature'] = (self.solar_controller["temperatures"][0] >> 0 & 0xff) # <-- lower 8 bits
            self._dbusservice['/MppTemperature'] = (self.solar_controller["temperatures"][0] >> 8 & 0xff) # <-- lower 8 bits

            self._dbusservice['/Pv/V'] = (self.solar_controller["solar_voltage"][0] / 10)
            self._dbusservice['/Pv/P'] = (self.solar_controller["solar_power"][0])
            self._dbusservice['/Yield/Power'] = (self.solar_controller["solar_power"][0]) # in Wh (System yield in GUI)
            self._dbusservice['/Yield/User'] = (self.solar_controller["power_gen_day"][0]) # in Wh (Total yield in GUI)

            self._dbusservice['/History/Overall/DaysAvailable'] = (self.solar_controller["uptime"][0])
            self._dbusservice['/History/Daily/0/Yield'] = (self.solar_controller["power_gen_day"][0] / 1000) # in watts
            self._dbusservice['/History/Daily/0/MaxPower'] = (self.solar_controller["max_power_day"][0]) # in watts

            # mppt_state is the current method the battery is being charged (bulk, absortion, float)
            mptt_state = _calculate_state(self.solar_controller["load_status"][0],\
                                     self.solar_controller["solar_current"][0] * 0.01,\
                                     self.solar_controller["battery_voltage"][0] / 10)
            self._dbusservice['/State'] = mptt_state

            # set the /Mode and /DeviceOffReason
            if mptt_state == 0:
                self._dbusservice['/Mode'] = 4 # off
                self._dbusservice['/DeviceOffReason'] = 1 # no/low input power
            else:
                self._dbusservice['/Mode'] = 1 # on
                self._dbusservice['/DeviceOffReason'] = None # unset?


            # it costs us very little to update the same variables in memory (this isn't low latency programming)
            # 0dhist': [115, 0, 248, 145, 131] charge Wh/today, load today, max power gen today (watt), max battery, min battery
            for day in range(int(history_days)):
                history_key = str(day) + "hist"

                # these are all stored on the mppt
                self._dbusservice[f"/History/Daily/{day}/Yield"] = (self.solar_controller[history_key][0] / 1000) # labeled as kWh in GUI, ms4840 reports WH
                self._dbusservice[f"/History/Daily/{day}/MaxPower"] = (self.solar_controller[history_key][2])
                self._dbusservice[f"/History/Daily/{day}/MaxBatteryVoltage"] = ((self.solar_controller[history_key][3]) / 10)
                self._dbusservice[f"/History/Daily/{day}/MinBatteryVoltage"] = ((self.solar_controller[history_key][4]) / 10)

            # if we have a new maximum battery current, reflect it today - this is not stored on the ms4840n
            if self._dbusservice['/Dc/0/Current'] > self._dbusservice['/History/Daily/0/MaxBatteryCurrent']:
                self._dbusservice['/History/Daily/0/MaxBatteryCurrent'] = self._dbusservice['/Dc/0/Current']
                self.solar_controller['MaxBatteryCurrent'] = self._dbusservice['/Dc/0/Current']

            # if we have a new maximum solar voltage, reflect it today - this is not stored on the ms4840n
            if self._dbusservice['/Pv/V'] > self._dbusservice['/History/Daily/0/MaxPvVoltage']:
                self._dbusservice['/History/Daily/0/MaxPvVoltage'] = self._dbusservice['/Pv/V']
                self.solar_controller['MaxPvVoltage'] = self._dbusservice['/Pv/V']

            # do we have a new min/max overall battery voltage
            if self._dbusservice['/Dc/0/Voltage'] > self._dbusservice['/History/Overall/MaxBatteryVoltage']:
                self._dbusservice['/History/Overall/MaxBatteryVoltage'] = self._dbusservice['/Dc/0/Voltage']
            if self._dbusservice['/Dc/0/Voltage'] < self._dbusservice['/History/Overall/MinBatteryVoltage']:
                self._dbusservice['/History/Overall/MinBatteryVoltage'] = self._dbusservice['/Dc/0/Voltage']

            # do we have a new overall solar voltage - this is not storage on the ms4840n
            if self._dbusservice['/Pv/V'] > self._dbusservice['/History/Overall/MaxPvVoltage']:
                self._dbusservice['/History/Overall/MaxPvVoltage'] = self._dbusservice['/Pv/V']

            # total power generation all time in WH
            self._dbusservice['/Yield/System'] = (self.solar_controller['total_power_generation'][1])

            # any errors - https://www.victronenergy.com/live/mppt-error-codes
            self._dbusservice['/ErrorCode'] = _get_errorcode(self.solar_controller["alarm_info"][0])


        # midnight! (or close to it in case we miss the exact midnight hour)
        hours, minutes, seconds = _calculate_midnight()
        if hours == 0 and minutes == 0 and (seconds >= 0 or seconds <= 2):
            self._update_history(hours, minutes, seconds)

        # increment UpdateIndex - to show that new data is available
        self.loop_index = self._dbusservice["/UpdateIndex"] + 1  # increment index
        if self.loop_index > 255:  # maximum value of the index
            self.loop_index = 0  # overflow from 255 to 0
        self._dbusservice["/UpdateIndex"] = self.loop_index

        # calculate the elapsed time and report it if debugging is enabled
        elapsed_time = (time.process_time() - start_time)
        if self.debugging == True:
            logger.debug("spent %f in _update" % (elapsed_time))
            logger.debug(f'{self.solar_controller}')

        # and we're done - always return True
        return True

def main():
    global servicename
    global debugging

    # gratuitously copied from mrmanual
    def handle_exit_signal(signum, frame, code: int = 0):
        logger.info("Exit signal received, exiting gracefully...")
        if "mainloop" in globals() and mainloop is not None:
            mainloop.quit()
        
        # and we're out
        logger.info(f"stopped dbus-ms4840: exit code: {code}")
        sys.exit(code)

    # use SIGUSR1 to toggle debugging
    def handle_usr1_signal(signum):
        global debugging

        current_level = logging.getLogger().getEffectiveLevel()
        if current_level > logging.DEBUG:
            logger.info('debug logging on')
            logging.getLogger().setLevel(logging.DEBUG)
            debugging = True
        else:
            logging.getLogger().setLevel(logging.INFO)
            logger.info('debug logging off')
            debugging = False

    # register the signal handler(s)
    signal.signal(signal.SIGINT, handle_exit_signal)
    signal.signal(signal.SIGTERM, handle_exit_signal)
    signal.signal(signal.SIGUSR1, handle_usr1_signal)

    from dbus.mainloop.glib import DBusGMainLoop
    # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
    DBusGMainLoop(set_as_default = True)

    # add to the dbus paths
    paths_dbus = {
        "/UpdateIndex": {"value": 0, "textformat": _n},
    }
    solar_charger_dict.update(paths_dbus)

    # create a dbus helper that does some stuff
    helper = DbusHelper(1, servicename)
    helper.create_pid_file()

    # create the mppt solar charger object
    ms4840 = MS4840(paths = solar_charger_dict)

    # and off to the races we go
    logger.info(f'Welcome to dbus-ms4840 version {softwareversion} (c) Serron Zub (serronzub@gmail.com)')
    logger.info(f'Venus OS {get_venus_os_version()} ({get_venus_os_image_type()}) running on + {get_venus_os_device_type()}')
    logger.info('Connected to dbus, and switching over to GLib.MainLoop() (= event based)')

    # create a GLib loop
    mainloop = GLib.MainLoop()
    # add the signal to the mainloop
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, handle_usr1_signal, None)
    try:
        mainloop.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    debugging = True
    main()


"""
example of solar_controller dict
DEBUG:ms4840:{'sver': [121], 'hver': [100], 'system_info': [8224, 19795, 11572, 14388, 12366, 8224, 8224, 8224], 
              'load_status': [4], 'current_system_voltage': [12], 'battery_power': [100], 'battery_voltage': [146],
              'solar_current': [55], 'solar_power': [8], 'temperatures': [8737], 'solar_voltage': [417],
              'max_power_day': [248], 'power_gen_day': [205], 'alarm_info': [0], 'battery_type': [4], 'uptime': [51],
              'total_power_generation': [0, 8550], '0dhist': [205, 0, 248, 147, 131], '1dhist': [21, 0, 28, 147, 132],
              '0hist': [205, 0, 248, 147, 131], '1hist': [21, 0, 28, 147, 132], '2hist': [58, 0, 93, 147, 112],
              '3hist': [139, 0, 209, 146, 132], '4hist': [276, 0, 119, 147, 129], '5hist': [68, 0, 56, 147, 132],
              '6hist': [202, 0, 117, 147, 132], '7hist': [199, 0, 90, 147, 132], '8hist': [65, 0, 39, 145, 132],
              '9hist': [66, 0, 39, 145, 133], '10hist': [60, 0, 148, 144, 132], '11hist': [63, 0, 36, 145, 132],
              '12hist': [185, 0, 136, 145, 133], '13hist': [138, 0, 64, 135, 133], '14hist': [232, 0, 225, 144, 132],
              '15hist': [60, 0, 62, 135, 130], '16hist': [5, 0, 21, 133, 130], '17hist': [291, 0, 329, 145, 130],
              '18hist': [137, 0, 198, 145, 131], '19hist': [247, 0, 264, 144, 132], '20hist': [134, 0, 88, 147, 132],
              '21hist': [19, 0, 14, 135, 132], '22hist': [65, 0, 54, 136, 70], '23hist': [108, 0, 24, 135, 132],
              '24hist': [703, 0, 280, 138, 129], '25hist': [87, 0, 126, 145, 130], '26hist': [13, 0, 6, 145, 134],
              '27hist': [12, 0, 6, 145, 135], '28hist': [12, 0, 7, 145, 135], '29hist': [12, 0, 6, 145, 134]}
"""
