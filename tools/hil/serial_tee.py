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
# The USB link on this board drops and re-enumerates on reset (the
# ttyACM number can even change), so reads/writes retry with re-open
# exactly like serial_run.py; the PTY stays up throughout.
import argparse
import glob
import os
import pty
import select
import sys
import time

import serial
import termios
import tty


def open_port(baud):
    """Re-locate and open the board port; None while it is gone."""
    for p in sorted(glob.glob("/dev/ttyACM*")):
        try:
            return serial.Serial(p, baud, timeout=0)
        except serial.SerialException:
            continue
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--pty", default="/tmp/demo-serial")
    ap.add_argument("--log", required=True)
    args = ap.parse_args()

    ser = open_port(args.baud)
    mfd, sfd = pty.openpty()
    tty.setraw(mfd)
    # SiliconLoop: raw mode must be set on the SLAVE, whose line
    # discipline is what echoes. With ECHO on, every board->terminal
    # byte is echoed back into the master and this loop forwards it to
    # the board as keyboard input (boot banner text became garbage
    # commands on the 2026-11-04 demo attempt 1).
    tty.setraw(sfd)
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
    try:
        while True:
            fds = [mfd] + ([ser.fileno()] if ser else [])
            r, _, _ = select.select(fds, [], [], 1.0)
            if ser and ser.fileno() in r:
                try:
                    data = ser.read(4096)
                except (serial.SerialException, OSError):
                    # board reset: the port dropped. Re-locate and retry;
                    # the terminal side never notices.
                    try:
                        ser.close()
                    except Exception:
                        pass
                    ser = None
                    time.sleep(1.0)
                    continue
                if data:
                    logf.write(data)      # watcher sees board output
                    try:
                        os.write(mfd, data)   # terminal sees board output
                    except OSError:
                        pass
            if mfd in r:
                data = os.read(mfd, 4096)
                if data:
                    for _ in range(5):
                        if ser is None:
                            time.sleep(1.0)
                            ser = open_port(args.baud)
                            if ser is None:
                                continue
                        try:
                            ser.write(data)   # keyboard -> board
                            break
                        except (serial.SerialException, OSError):
                            try:
                                ser.close()
                            except Exception:
                                pass
                            ser = None
                            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        logf.close()
        os.close(mfd)
        os.close(sfd)
        if ser:
            try:
                ser.close()
            except Exception:
                pass
        try:
            os.unlink(args.pty)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
