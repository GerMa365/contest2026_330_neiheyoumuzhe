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
    ser = serial_run.open_port(port)
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

    # start the transfer
    send(f"fwpush {len(data)} {checksum:08x}\r")
    resp = drain(0.5)

    b64 = base64.b64encode(data).decode()
    for i in range(0, len(b64), args.chunk):
        send(b64[i:i + args.chunk] + "\r", wait=args.pace)
    send("fwpush_end\r")
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
