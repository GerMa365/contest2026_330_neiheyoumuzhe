#!/usr/bin/env python3
# SiliconLoop HIL: serial_tee - share one serial port between a recorded
# terminal and a live log watcher (demo-video run, 2026-11-04).
#
# The board's /dev/ttyACM0 can be opened by only one process, but the
# demo video needs (a) Ghee typing in a real terminal while recording,
# and (b) Claude watching the same bytes to announce key log lines.
# This script holds the real port, creates a PTY in its place and
# bridges both directions byte-for-byte, mirroring board->terminal
# bytes into a log file for the watcher.
#
#   serial_tee.py [--port /dev/ttyACM0] [--baud 115200]
#                 [--pty /tmp/demo-serial] --log /path/demo-tee.log
#
# Terminal side:  picocom -b 115200 /tmp/demo-serial
# Watcher side:   tail -f /path/demo-tee.log
#
# Board reset: press the board's physical RST button (the video can
# show it) - RTS/DTR from the terminal goes to the PTY, not the port.
import argparse
import os
import pty
import select
import sys

import serial
import termios
import tty


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--pty", default="/tmp/demo-serial")
    ap.add_argument("--log", required=True)
    args = ap.parse_args()

    ser = serial.Serial(args.port, args.baud, timeout=0)
    mfd, sfd = pty.openpty()
    tty.setraw(mfd)
    # expose the slave under a stable path for the terminal
    slave = os.ttyname(sfd)
    try:
        os.unlink(args.pty)
    except FileNotFoundError:
        pass
    os.symlink(slave, args.pty)
    print(f"[tee] {args.port} <-> {args.pty} -> {slave}; log {args.log}",
          flush=True)

    logf = open(args.log, "ab", buffering=0)
    fds = [ser.fileno(), mfd]
    try:
        while True:
            r, _, _ = select.select(fds, [], [])
            if ser.fileno() in r:
                data = ser.read(4096)
                if data:
                    logf.write(data)      # watcher sees board output
                    os.write(mfd, data)   # terminal sees board output
            if mfd in r:
                data = os.read(mfd, 4096)
                if data:
                    ser.write(data)       # keyboard -> board
    except KeyboardInterrupt:
        pass
    finally:
        logf.close()
        os.close(mfd)
        os.close(sfd)
        ser.close()
        try:
            os.unlink(args.pty)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
