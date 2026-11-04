#!/usr/bin/env python3
# SiliconLoop HIL: locate the ESP32-P4 USB-Serial/JTAG port by USB ID.
# The port number (ttyACM0/1/...) shifts after every reset/re-flash, so the
# scripts must not hardcode it. Returns the path on stdout, or exits 2.

import glob
import re
import sys

USB_ID = "303A:1001"   # Espressif USB JTAG/serial debug unit (VID:PID, case-insensitive)

def find_port():
    import serial.tools.list_ports
    for p in serial.tools.list_ports.comports():
        hwid = (p.hwid or "").upper()
        if USB_ID in hwid:
            return p.device
    return None

if __name__ == "__main__":
    port = find_port()
    if port:
        print(port)
    else:
        sys.exit(2)
