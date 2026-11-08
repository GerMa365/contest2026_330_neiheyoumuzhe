#!/usr/bin/env python3
# SiliconLoop M4 HIL: push the hotfix payload (buggy_app_fixed ELF) to the
# board over the serial line using the vela CLI "fwpush" command.
#
# The ELF is built by the apps framework to apps/bin/buggy_app_fixed
# (MODULE=m relocatable). It lands on the board at
# /data/patches/buggy_app_fixed, base64-encoded in chunks, guarded by
# size + FNV-1a-32 checksum verified BY THE BOARD on readback (transport
# bit-error guard only - not an authenticity check).
#
# Usage:
#   python3 push_hotfix.py [--elf apps/bin/buggy_app_fixed] [--port /dev/ttyACM0]
#
# The board must be at a shell prompt (nsh> or vela>). If ai_agent owns
# the console, send "quit" first (the script exits nonzero asking you to
# re-run, or use --quit-first).

import argparse
import base64
import serial
import sys
import time


def fnv1a32(data: bytes) -> int:
    h = 0x811C9DC5
    for b in data:
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--elf", default=None,
                    help="path to buggy_app_fixed ELF (default: "
                         "<workspace>/apps/bin/buggy_app_fixed)")
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=115200,
                    help="console baud (not the flash baud)")
    ap.add_argument("--quit-first", action="store_true",
                    help="send 'quit' first in case ai_agent owns the "
                         "console")
    ap.add_argument("--chunk", type=int, default=32,
                    help="base64 chars per line (default 32; the board "
                         "UART RX buffer is 256B, keep lines small)")
    ap.add_argument("--pace", type=float, default=0.05,
                    help="seconds between lines (default 0.05)")
    args = ap.parse_args()

    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    # reuse the serial machinery from serial_run.py
    import serial_run  # noqa: E402

    elf = args.elf
    if not elf:
        # <workspace>/apps/bin/buggy_app_fixed relative to this script:
        # tools/hil -> repo -> openvela root
        import os
        root = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", ".."))
        elf = os.path.join(root, "apps", "bin", "buggy_app_fixed")

    with open(elf, "rb") as f:
        data = f.read()
    if len(data) > 16 * 1024:
        print(f"ERROR: {elf} is {len(data)} bytes, over the 16KB fwpush "
              "limit", file=sys.stderr)
        return 2
    checksum = fnv1a32(data)
    print(f"pushing {elf}: {len(data)} bytes, fnv1a={checksum:08x}")

    port = serial_run.locate_port() if args.port == "auto" else args.port
    # SiliconLoop: serial_run.open_port(timeout) takes a TIMEOUT, not a
    # port name - open the device directly here (console is at 115200).
    ser = serial.Serial(port, 115200, timeout=0.3)
    if ser is None:
        print(f"ERROR: cannot open {port}", file=sys.stderr)
        return 2

    def send(s, wait=0.05):
        ser.write(s.encode())
        time.sleep(wait)

    def drain(t=0.4):
        out = b""
        end = time.time() + t
        while time.time() < end:
            chunk = ser.read(4096)
            if chunk:
                out += chunk
                end = time.time() + 0.2
        return out.decode(errors="replace")

    if args.quit_first:
        send("quit\r")
        drain(1.0)

    # SiliconLoop: fwpush lives in ai_agent's vela> CLI, and BOTH shells
    # (nsh and agent_cli) read the same UART - whichever task wins the
    # stdin race gets the line (seen 06:43: every base64 chunk answered
    # "command not found" by nsh). So: make sure ai_agent is running,
    # then hand it a line and wait until it answers from the vela> side
    # before streaming the payload.
    # Long first drain: a fresh boot keeps printing for seconds, and a
    # too-short probe made us start a SECOND agent instance (rc=-1 on
    # nsh_commands_start, seen 06:47).
    boot = b""
    deadline = time.time() + 6
    while time.time() < deadline:
        chunk = ser.read(4096)
        if chunk:
            boot += chunk
            deadline = time.time() + 1.5
    boot = boot.decode(errors="replace")
    agent_running = ("[agent]" in boot or "vela>" in boot
                     or "[heartbeat]" in boot)
    if "vela>" not in boot:
        if not agent_running:
            # ai_agent not running at all - start it (foreground so its
            # CLI thread owns stdin) and wait for the vela> prompt.
            send("ai_agent\r")
        # Either way, wait for the CLI to answer: a heartbeat round in
        # flight can hold the console for tens of seconds; the prompt
        # only prints when the CLI thread gets its turn.
        deadline = time.time() + 90
        acc = boot
        while time.time() < deadline:
            acc += drain(1.0)
            if "vela>" in acc:
                break
        else:
            print("ERROR: no vela> prompt after starting ai_agent; "
                  "board said:", file=sys.stderr)
            print(acc[-800:], file=sys.stderr)
            return 2

    # prompt sync: an empty line must bounce back a fresh "vela>" from
    # the agent CLI (proves the CLI owns stdin right now)
    for _ in range(5):
        send("\r")
        if "vela>" in drain(1.0):
            break
    else:
        print("ERROR: vela> prompt never re-answered; aborting",
              file=sys.stderr)
        return 2

    # probe: a bare "fwpush" must return the usage line FROM THE VELA
    # CLI. If nsh answered instead ("command not found"), the header we
    # send next would be eaten by the wrong shell (seen 07:00: every
    # chunk answered "Unknown command" because nsh took the header).
    probe_tries = 5
    for _ in range(probe_tries):
        send("fwpush\r")
        r = drain(1.0)
        if "usage: fwpush" in r:
            break
        if "vela>" not in r:
            send("\r")
            drain(0.8)
    else:
        print("ERROR: fwpush probe failed (vela CLI does not own "
              "stdin)", file=sys.stderr)
        return 2

    # SiliconLoop: use \n line endings (the \r-only variant lost lines
    # mid-stream once the transfer started, seen 06:50-06:55); drain
    # DURING streaming so a mid-transfer board verdict is seen in the
    # right order and the UART echo cannot back up.
    #
    # SiliconLoop: do NOT push while a heartbeat LLM round is running.
    # The agent round holds the console busy for 10-90s; the vela CLI
    # stops draining the 256B UART RX ring, bytes drop mid-chunk and
    # the board answers "fwpush: bad chunk (n=-1, ...)" (seen 07:0x:
    # got=2904 / 3768 at different offsets, always during a round).
    # Wait for the console to go quiet (no LLM activity for 8s) first;
    # scenario.py's 3-attempt retry covers a round that fires anyway.
    quiet_deadline = time.time() + 150
    while time.time() < quiet_deadline:
        r = drain(2.0)
        if "[llm] OpenAI API" in r or "[trace" in r and "BEGIN" in r:
            continue            # a round is in flight; keep waiting
        if "[trace" in r and "END status=" in r:
            break               # round just finished; quiet window now
        # no activity in this window - quiet enough to start
        if r.strip() == "" or "vela>" in r:
            break
    else:
        print("ERROR: console never went quiet (heartbeat rounds keep "
              "firing); aborting", file=sys.stderr)
        return 2

    send(f"fwpush {len(data)} {checksum:08x}\n")
    resp = drain(0.5)
    if "Unknown command" in resp or "nsh:" in resp:
        print("ERROR: header eaten by the wrong shell; board said:",
              file=sys.stderr)
        print(resp[-400:], file=sys.stderr)
        return 1

    b64 = base64.b64encode(data).decode()
    aborted = False
    for i in range(0, len(b64), args.chunk):
        send(b64[i:i + args.chunk] + "\n", wait=args.pace)
        r = drain(0.1)
        # a board verdict mid-stream means the transfer already ended
        # (bad chunk / checksum) - stop streaming, capture the verdict
        if "fwpush:" in r:
            resp += r
            aborted = True
            break
        # nsh ate this chunk (dispatch rejection noise) - abort; the
        # board will fail the transfer and unlink, caller retries
        if "Unknown command: " + b64[i:i + args.chunk] in r \
                or "command not found" in r:
            resp += r
            aborted = True
            break
        resp += r
    if not aborted:
        send("fwpush_end\n")
        resp += drain(4.0)
    else:
        # flush whatever the board still prints for this transfer
        resp += drain(2.0)

    if "fwpush: OK" in resp:
        ok_line = [l for l in resp.splitlines() if "fwpush: OK" in l][-1]
        print(ok_line.strip())
        return 0
    print("ERROR: fwpush did not confirm; board said:")
    print(resp[-800:])
    return 1


if __name__ == "__main__":
    sys.exit(main())
