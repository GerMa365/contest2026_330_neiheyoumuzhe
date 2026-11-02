#!/usr/bin/env python3
# SiliconLoop HIL: serial session runner.
#
# Opens the board's USB-Serial/JTAG port (located by USB ID, not by name —
# the ttyACM number shifts after every reset/re-flash), optionally hard-resets
# via RTS/DTR, waits for the nsh prompt, sends commands, and saves every byte
# exchanged to a timestamped log.
#
# The USB link on this board is flaky ("device reports readiness to read but
# returned no data", occasional disconnects on reset). Everything here assumes
# the port can vanish mid-session: reads catch, close, re-locate and re-open.
#
# Usage:
#   python3 serial_run.py [--reset] [--logfile out.log] [--timeout 30] \
#                         -- "uname -a" free ps
#
# Exit codes: 0 = nsh prompt seen, all commands sent; 2 = board not reachable.

import argparse
import json
import subprocess
import sys
import time

import serial

NSH_PROMPT = "nsh> "
FIND_PORT = __file__.replace("serial_run.py", "find_port.py")

def locate_port():
    out = subprocess.run([sys.executable, FIND_PORT],
                         capture_output=True, text=True, timeout=10)
    return out.stdout.strip() or None

def open_port(timeout=0.3):
    port = locate_port()
    if not port:
        return None
    try:
        return serial.Serial(port, 115200, timeout=timeout)
    except serial.SerialException:
        return None

class Link:
    # Owns the serial port and survives device re-enumeration.
    def __init__(self):
        self.s = open_port()

    def read(self, n):
        for _ in range(8):
            if self.s is None:
                time.sleep(1.0)
                self.s = open_port()
                if self.s is None:
                    continue
            try:
                return self.s.read(n)
            except serial.SerialException:
                try:
                    self.s.close()
                except Exception:
                    pass
                self.s = None
                time.sleep(1.0)
        return b""

    def write(self, data):
        for _ in range(5):
            if self.s is None:
                time.sleep(1.0)
                self.s = open_port()
                if self.s is None:
                    continue
            try:
                self.s.write(data)
                self.s.flush()
                return True
            except serial.SerialException:
                try:
                    self.s.close()
                except Exception:
                    pass
                self.s = None
                time.sleep(1.0)
        return False

    def reset(self):
        # Hard reset via RTS on the USB-Serial/JTAG interface. The port drops
        # and re-enumerates (possibly with a new ttyACM number).
        try:
            if self.s:
                self.s.rts = True
                self.s.dtr = False
                time.sleep(0.1)
                self.s.rts = False
                self.s.close()
        except Exception:
            pass
        self.s = None
        time.sleep(2)
        # wait for the device to come back (up to 15 s, path may change)
        deadline = time.time() + 15
        while time.time() < deadline:
            if locate_port():
                time.sleep(1)   # let the driver settle
                return True
            time.sleep(0.5)
        return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="hard-reset first")
    ap.add_argument("--logfile", required=True)
    ap.add_argument("--timeout", type=int, default=30,
                    help="seconds to wait for the nsh prompt")
    ap.add_argument("cmds", nargs="*", help="commands to run, in order")
    args = ap.parse_args()

    logf = open(args.logfile, "ab")
    logf.write(f"\n===== session {time.strftime('%F %T')} "
               f"reset={args.reset} =====\n".encode())

    link = Link()
    if args.reset and not link.reset():
        print(json.dumps({"ok": False, "error": "board did not re-enumerate"}))
        sys.exit(2)

    # wait for the nsh prompt; nudge with newlines because a fresh session may
    # find the shell already idle with no unsolicited output
    deadline = time.time() + args.timeout
    buf = b""
    ok = False
    last_nudge = 0.0
    while time.time() < deadline:
        if time.time() - last_nudge > 2.0:
            link.write(b"\n")
            last_nudge = time.time()
        data = link.read(4096)
        if data:
            buf += data
            logf.write(data)
            logf.flush()
            if NSH_PROMPT.encode() in buf:
                ok = True
                break

    if ok:
        for cmd in args.cmds:
            logf.write(f"\n[{time.strftime('%H:%M:%S')}] CMD {cmd}\n".encode())
            link.write((cmd + "\n").encode())
            # collect output until a fresh prompt or 10 s of silence
            deadline = time.time() + 10
            tail = b""
            while time.time() < deadline:
                data = link.read(4096)
                if data:
                    tail += data
                    logf.write(data)
                    logf.flush()
                    deadline = time.time() + 3   # reset silence window
                    if tail.rstrip().endswith(NSH_PROMPT.strip().encode()):
                        break
        logf.write(f"\n[{time.strftime('%H:%M:%S')}] SESSION OK\n".encode())
        print(json.dumps({"ok": True, "cmds": len(args.cmds)}))
    else:
        logf.write(f"\n[{time.strftime('%H:%M:%S')}] NO NSH PROMPT\n".encode())
        print(json.dumps({"ok": False,
                          "error": "no nsh prompt", "rx_bytes": len(buf)}))
        sys.exit(2)
    logf.close()

if __name__ == "__main__":
    main()
