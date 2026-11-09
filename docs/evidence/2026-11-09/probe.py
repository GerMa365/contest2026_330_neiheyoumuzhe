#!/usr/bin/env python3
"""SiliconLoop M4 vs defense firmware memory probe (Ghee 2026-11-09)."""
import glob, re, serial, sys, time

def newest_port():
    ps = sorted(glob.glob("/dev/ttyACM*"))
    return ps[-1] if ps else "/dev/ttyACM0"

def main():
    label, logfile = sys.argv[1], sys.argv[2]
    all_out = bytearray()
    ser = serial.Serial(newest_port(), 115200, timeout=0.5)

    def drain(t):
        nonlocal ser
        end = time.time() + t
        while time.time() < end:
            try:
                b = ser.read(4096)
            except serial.SerialException:
                try: ser.close()
                except Exception: pass
                time.sleep(1.0)
                ser = serial.Serial(newest_port(), 115200, timeout=0.5)
                continue
            if b:
                all_out.extend(b)
                end = time.time() + 0.3

    def send(line):
        nonlocal ser
        try:
            ser.write((line + "\n").encode()); ser.flush()
        except serial.SerialException:
            try: ser.close()
            except Exception: pass
            time.sleep(1.0)
            ser = serial.Serial(newest_port(), 115200, timeout=0.5)
            ser.write((line + "\n").encode()); ser.flush()

    def text():
        return all_out.decode(errors="replace")

    # 1. hard reset via RTS
    ser.setDTR(False); ser.setRTS(True)
    time.sleep(0.2)
    ser.setRTS(False)
    # wait for nsh prompt, up to 20s
    deadline = time.time() + 20
    while time.time() < deadline:
        drain(1.0)
        if "nsh>" in text():
            break
    else:
        print(f"{label}: WARN no nsh prompt in 20s", flush=True)
    time.sleep(1.0)

    # 2-3. inject buggy_app + ai_agent, capture agent_start_free
    send("buggy_app &")
    time.sleep(1.5)
    send("ai_agent")
    start_free = None
    deadline = time.time() + 40
    while time.time() < deadline:
        drain(1.0)
        m = re.search(r"free heap: (\d+)", text())
        if m:
            start_free = int(m.group(1))
            break
    print(f"{label}: agent_start_free={start_free}", flush=True)

    # 4. wait for the FIRST heartbeat round to END, then quit to nsh
    #    and sample maxfree there (same point as m4-smoke3-boot.log:
    #    post-boot static watermark; sampling DURING the request window
    #    is not possible without disturbing the round - nsh free needs
    #    the console, which vela CLI owns while the agent runs).
    req_seen = False
    maxfree = None
    deadline = time.time() + 240
    while time.time() < deadline:
        drain(1.0)
        t = text()
        if not req_seen and ("OpenAI API" in t or "ssl_handshake" in t):
            req_seen = True
        if req_seen and ("END status=" in t or "[trace" in t
                         and "END" in t):
            break
    send("quit")                # vela CLI -> nsh (stops the agent)
    time.sleep(1.0)
    send("free")
    drain(3.0)
    # data row: " total used free maxused maxfree nused nfree name"
    m = re.search(r"\d+\s+\d+\s+\d+\s+\d+\s+(\d+)\s+\d+\s+\d+\s+\w+", text())
    maxfree = int(m.group(1)) if m else None
    print(f"{label}: maxfree@nsh={maxfree} req_seen={req_seen}",
          flush=True)

    with open(logfile, "a") as f:
        f.write(f"\n===== {label} =====\n")
        f.write(text())
    ser.close()
    print(f"{label}: RESULT start_free={start_free} maxfree={maxfree}",
          flush=True)

if __name__ == "__main__":
    main()
