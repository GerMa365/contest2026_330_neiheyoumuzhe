#!/usr/bin/env python3
# SiliconLoop forensics: drive one full agent session WITHOUT reset at the
# end, so /data (tmpfs) evidence survives for inspection. Listens until a
# "API error 400" shows up or the budget expires, then quits the vela CLI
# and cats last_request.json into the capture log.
import re, subprocess, sys, time

import serial

HERE = "/home/w/Project/openvela/contest2026_330_neiheyoumuzhe/tools/hil"
BUDGET = 620  # seconds; the 400 strikes at the 2nd heartbeat ~350-450s in
OUT = "/tmp/dump-capture.log"


def find_port():
    out = subprocess.run([sys.executable, HERE + "/find_port.py"],
                         capture_output=True, text=True).stdout.strip()
    return out


def main():
    port = find_port()
    print("port:", port, flush=True)
    s = serial.Serial(port, 115200, timeout=0.5)
    log = open(OUT, "wb")

    def drain(t):
        end = time.time() + t
        buf = b""
        while time.time() < end:
            try:
                d = s.read(4096)
            except Exception:
                break
            if d:
                buf += d
                log.write(d)
                log.flush()
                end = time.time() + 0.4
        return buf

    # hard reset via RTS/DTR
    s.dtr = True
    s.rts = True
    time.sleep(0.1)
    s.rts = False
    time.sleep(0.1)
    s.dtr = False
    drain(12)

    def send(line):
        for ch in line:
            s.write(ch.encode())
            s.flush()
            time.sleep(0.01)
        s.write(b"\n")
        s.flush()

    drain(1)
    send("buggy_app &")
    drain(3)
    send("ai_agent")
    buf = drain(3)
    saw_400 = False
    deadline = time.time() + BUDGET
    tail = b""
    while time.time() < deadline:
        try:
            d = s.read(4096)
        except Exception:
            d = b""
        if d:
            log.write(d)
            log.flush()
            tail = (tail + d)[-2000:]
            if b"API error 400" in tail:
                saw_400 = True
                # give the agent a moment to write the dump file
                drain(3)
                break

    print("saw_400:", saw_400, "at", time.strftime("%H:%M:%S"), flush=True)
    # leave the vela CLI so nsh can run cat; then fetch the dump
    send("quit")
    drain(2)
    send("cat /data/ai_agent/evidence/last_request.json")
    drain(10)
    s.close()
    log.close()
    print("capture written to", OUT, flush=True)


if __name__ == "__main__":
    main()
