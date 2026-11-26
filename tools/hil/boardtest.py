#!/usr/bin/env python3
# SiliconLoop HIL: boardtest - single-recorder board test driver.
#
# 2026-11-24 lesson (cc-report-1124-fail): the A/B sections mixed a test
# script with inline observers, and bytes from two observation windows
# never landed in the raw log ("observer passed but not captured"). This
# driver removes the failure mode structurally:
#
#   * ONE process owns the serial port (via serial_run.Link, hardened
#     against USB re-enumeration) from hard reset to finish. Every byte
#     read is appended to the raw file before anything else happens.
#   * ALL actions - starting buggy_app, starting ai_agent, heap_info,
#     the fwpush payload push, quit - go through this same process.
#     No second serial.Serial() may exist while boardtest runs: do NOT
#     invoke push_hotfix.py alongside it, the push protocol is built in.
#
# 2026-11-25 lesson (tech-debt batch 2 / H1): a whole round that never
# landed in the raw log (A-r2) was invisible to logcheck, which can only
# check trace lines that exist. The driver therefore writes its OWN round
# markers into the raw log:
#
#   # host: [boardtest] round N start
#   # host: [boardtest] round N end
#
# logcheck now requires every round-start window to contain exactly one
# BEGIN/END pair, so a silently missed round is a hard violation instead
# of an undetectable gap.
#
# Cold-boot sequence is FIXED (Ghee, 2026-11-24):
#   reset -> nsh -> "buggy_app &" -> wait "buggy_app: producing"
#   -> "ai_agent" -> [--push: fwpush in the quiet window] -> N observed
#   rounds (heap_info after each) -> quit.
# A cold boot that never prints the producing line is INVALID (rc=10):
# buggy_app is the only writer of heartbeat.txt, so rounds observed
# without it are not acceptance evidence (the 2026-11-24 board test ran
# its whole A/B section with buggy_app never started).
#
# Usage:
#   python3 boardtest.py --raw out.raw cold [--rounds 3] [--push]
#                        [--elf PATH] [--chunk 252] [--pace 0.02]
#   python3 boardtest.py --raw out.raw watch [--seconds 600]
#   python3 boardtest.py --raw out.raw cmd -- free ps
#
# Exit codes: 0 ok; 2 no serial port; 5 no nsh prompt; 6 round timeout;
# 7 agent start failed; 8 push gate failed; 9 stop-condition/crash hit;
# 10 cold boot invalid (no "buggy_app: producing" line).
import argparse
import base64
import re
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from serial_run import Link, locate_port  # noqa: E402

NSH_WAIT_S = 90
PRODUCING_WAIT_S = 30
AGENT_WAIT_S = 40
ROUND_BEGIN_WAIT_S = 200   # heartbeat fires every 120 s
ROUND_END_WAIT_S = 260     # a round can legally run 10 slow iters
QUIET = 0.3

RE_BEGIN = re.compile(r"\[trace:\w+\] BEGIN chat=(\w+)")
RE_END = re.compile(r"\[trace:\w+\] END status=(\w+) iters=(\d+) tools=(\d+)")
RE_IT0 = re.compile(r"iter=0[^\r\n]*llm=(\w+)")
RE_MEMPROBE = re.compile(
    r"\[sloop-memprobe\] peak pre-write req=(\d+) maxfree=(\d+) free=(\d+)")
RE_PRODUCING = re.compile(r"buggy_app: producing, heartbeat at (\S+)")
RE_STARTFREE = re.compile(r"Agent loop started, free heap: (\d+)")
RE_PSRAM_BANNER = re.compile(r"\[sloop-psram\][^\r\n]*")
RE_UMEM = re.compile(
    r"(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+Umem")
RE_PSRAM_LINE = re.compile(r"psram: arena=(\d+) free=(\d+) maxfree=(\d+)")
RE_ECHILD = re.compile(r"exit=unknown \(ECHILD\), (\d+) bytes")

CRASH_SIGS = [
    ("guru", re.compile(r"Guru Meditation")),
    ("exc", re.compile(r"riscv_exception")),
    ("assert", re.compile(r"up_assert|Assertion failed", re.I)),
    ("panic", re.compile(r"\bPANIC\b")),
]
STOP_SIGS = CRASH_SIGS + [
    ("ssl_alloc", re.compile(r"ssl_setup ret=0x7f00")),
    ("ssl_fail", re.compile(
        r"ssl_setup ret=0x[0-9a-f]+|ssl_handshake ret=-0x")),
    ("alloc", re.compile(r"alloc_fail=[1-9]")),
    ("enomem", re.compile(r"errno=12\b")),
    ("oom", re.compile(r"out of memory", re.I)),
    ("badjson", re.compile(r"400\s+Invalid JSON|Invalid JSON in request")),
    ("writefail", re.compile(r"Write request failed: -\d+")),
    # a disposal actually executed - acceptance tests must stop here
    ("recover_action", re.compile(r"\[recover\] verdict")),
]


def log(m):
    print(m, flush=True)


class Rec:
    """The single recorder: owns the Link and the raw file.

    drain() is the ONLY read path; every byte it gets is appended to
    the raw file immediately, so "passed but not captured" cannot
    happen by construction.
    """

    def __init__(self, raw_path):
        self.link = Link()
        self.raw = open(raw_path, "a", encoding="utf-8")
        self.buf = ""
        self.pos = 0

    def mark(self, event):
        line = "\n# host: %s %s\n" % (event, time.strftime("%H:%M:%S"))
        self.raw.write(line)
        self.raw.flush()
        log("# host: %s" % event)

    def drain(self, t):
        """Read for up to t seconds, keeping alive QUIET after the last
        byte (same semantics as the 11-24 scripts). Returns the text
        that arrived during this call."""
        start = len(self.buf)
        end = time.time() + t
        while True:
            data = self.link.read(4096)
            if data:
                self.buf += data.decode(errors="replace")
                self.raw.write(data.decode(errors="replace"))
                self.raw.flush()
                if len(self.buf) > 800000:
                    self.buf = self.buf[-400000:]
                    self.pos = max(0, self.pos - 400000)
                end = time.time() + QUIET if t >= QUIET else end
            if time.time() >= end:
                break
        return self.buf[start:]

    def new_text(self):
        t = self.buf
        cut = t.rfind("\n", self.pos)
        if cut < 0:
            return ""
        out = t[self.pos:cut + 1]
        self.pos = cut + 1
        return out

    def tail(self, n=2500):
        return self.buf[-n:]

    def send(self, line, quiet=0.2):
        if not self.link.write((line + "\n").encode()):
            raise RuntimeError("serial write failed (port gone?)")
        self.drain(quiet)


def scan(text, groups):
    return sorted({name for name, rx in groups if rx.search(text)})


def wait_nsh(rec, t_reset):
    deadline = time.time() + NSH_WAIT_S
    last_poke = 0.0
    while time.time() < deadline:
        rec.drain(0.5)
        if rec.tail(300).rstrip().endswith("nsh>"):
            return True, time.time() - t_reset
        if time.time() - last_poke >= 3.0:
            rec.link.write(b"\n")
            last_poke = time.time()
    return False, time.time() - t_reset


def start_buggy_app(rec):
    """Fixed t1 step: start buggy_app and REQUIRE its producing line.
    Returns (ok, heartbeat_path)."""
    rec.mark("t1 buggy_app & (fixed cold-boot step)")
    rec.send("buggy_app &", quiet=0.5)
    deadline = time.time() + PRODUCING_WAIT_S
    while time.time() < deadline:
        rec.drain(0.5)
        m = RE_PRODUCING.search(rec.buf)
        if m:
            log("BUGGY-APP producing: heartbeat at %s" % m.group(1))
            return True, m.group(1)
    log("COLD-INVALID: no 'buggy_app: producing' within %ds"
        % PRODUCING_WAIT_S)
    return False, None


def start_agent(rec, label):
    rec.mark("t2 ai_agent %s" % label)
    rec.send("ai_agent", quiet=1.0)
    deadline = time.time() + AGENT_WAIT_S
    while time.time() < deadline:
        rec.drain(0.5)
        if RE_STARTFREE.search(rec.buf):
            break
        if rec.tail(200).rstrip().endswith("nsh>"):
            log("RESULT %s agent_exited_early" % label)
            return None
    rec.drain(2.0)
    rec.mark("flush %s" % label)
    banners = RE_PSRAM_BANNER.findall(rec.buf)
    log("SLOOP-PSRAM %s: %s" % (label, banners if banners else "NONE"))
    return {"banners": banners}


def heap_info(rec, label):
    rec.mark("heap_info %s" % label)
    rec.send("heap_info", quiet=2.5)
    t = rec.tail(2500)
    m = RE_UMEM.search(t)
    sysheap = {"free": int(m.group(3)), "maxfree": int(m.group(5))} \
        if m else None
    pm = RE_PSRAM_LINE.search(t)
    psram = {"arena": int(pm.group(1)), "free": int(pm.group(2)),
             "maxfree": int(pm.group(3))} if pm else None
    log("HEAPINFO %s sys=%s psram=%s" % (label, sysheap, psram))
    return sysheap, psram


def watch_round(rec, label, idx):
    """Passively watch one full heartbeat round. rc 0=ended, 6=timeout,
    9=stop-condition/crash. Writes [boardtest] round N start/end markers
    into the raw log so logcheck can detect a round that never got
    captured at all (H1)."""
    data = {"probes": [], "end": None, "it0_llm": None, "echild": [],
            "hits": [], "begin": False}
    rec.pos = len(rec.buf)
    rec.mark("[boardtest] round %d start %s" % (idx, label))
    begin_at = None
    deadline = time.time() + ROUND_BEGIN_WAIT_S
    while True:
        rec.drain(1.0)
        for line in rec.new_text().splitlines():
            for name, rx in STOP_SIGS:
                if rx.search(line):
                    data["hits"].append(name)
            em = RE_ECHILD.search(line)
            if em:
                data["echild"].append(int(em.group(1)))
            if not data["begin"]:
                if RE_BEGIN.search(line):
                    data["begin"] = True
                    begin_at = time.time()
                    rec.mark("round %d BEGIN %s" % (idx, label))
            else:
                pm = RE_MEMPROBE.search(line)
                if pm:
                    data["probes"].append(
                        (int(pm.group(1)), int(pm.group(2)),
                         int(pm.group(3))))
                im = RE_IT0.search(line)
                if im and data["it0_llm"] is None:
                    data["it0_llm"] = im.group(1)
                m = RE_END.search(line)
                if m and data["end"] is None:
                    data["end"] = {"status": m.group(1),
                                   "iters": int(m.group(2)),
                                   "tools": int(m.group(3))}
        if data["end"] is not None:
            break
        if data["hits"]:
            log("ABORT round %d %s hits=%s"
                % (idx, label, sorted(set(data["hits"]))))
            rec.mark("[boardtest] round %d end %s (ABORT hits)"
                     % (idx, label))
            return 9, data
        if rec.tail(300).rstrip().endswith("nsh>"):
            log("ABORT round %d %s: agent back at nsh" % (idx, label))
            rec.mark("[boardtest] round %d end %s (ABORT nsh)"
                     % (idx, label))
            return 9, data
        now = time.time()
        if begin_at is None and now > deadline:
            log("RESULT round %d %s timeout: no BEGIN" % (idx, label))
            rec.mark("[boardtest] round %d end %s (TIMEOUT no BEGIN)"
                     % (idx, label))
            return 6, data
        if begin_at is not None and now > begin_at + ROUND_END_WAIT_S:
            log("RESULT round %d %s timeout: no END" % (idx, label))
            rec.mark("[boardtest] round %d end %s (TIMEOUT no END)"
                     % (idx, label))
            return 6, data
    rec.mark("[boardtest] round %d end %s" % (idx, label))
    log("ROUND %s r%d END=%s it0_llm=%s probes=%d echild=%s hits=%s"
        % (label, idx, data["end"], data["it0_llm"], len(data["probes"]),
           data["echild"], sorted(set(data["hits"]))))
    return 0, data


def fnv1a32(data):
    h = 0x811C9DC5
    for b in data:
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def do_push(rec, elf_path, chunk=252, pace=0.02):
    """In-process fwpush push (same gates as push_hotfix.py, but through
    the recorder's Link - no second serial owner). chunk<=252 keeps a
    full line + newline inside the board's 256B UART RX ring."""
    with open(elf_path, "rb") as f:
        data = f.read()
    if len(data) > 16 * 1024:
        log("PUSH-FAIL %s is %d bytes, over the 16KB fwpush limit"
            % (elf_path, len(data)))
        return 2
    checksum = fnv1a32(data)
    log("PUSH %s: %d bytes, fnv1a=%08x chunk=%d pace=%.3f"
        % (elf_path, len(data), checksum, chunk, pace))
    rec.mark("push start (in-process)")

    # vela> prompt sync: the agent CLI must own stdin right now
    ok = False
    for _ in range(5):
        rec.link.write(b"\r")
        if "vela>" in rec.drain(1.0):
            ok = True
            break
    if not ok:
        log("PUSH-FAIL no vela> prompt; agent CLI does not own stdin")
        return 2
    for _ in range(5):
        rec.link.write(b"fwpush\r")
        r = rec.drain(1.0)
        if "usage: fwpush" in r:
            break
        if "vela>" not in r:
            rec.link.write(b"\r")
            rec.drain(0.8)
    else:
        log("PUSH-FAIL fwpush probe failed (wrong shell owns stdin)")
        return 2

    # quiet window: never push while a heartbeat round holds the console
    quiet_deadline = time.time() + 150
    while time.time() < quiet_deadline:
        r = rec.drain(2.0)
        if "[llm] OpenAI API" in r or ("[trace" in r and "BEGIN" in r):
            continue
        if "[trace" in r and "END status=" in r:
            break
        if r.strip() == "" or "vela>" in r:
            break
    else:
        log("PUSH-FAIL console never went quiet")
        return 2

    rec.send("fwpush %d %08x" % (len(data), checksum), quiet=0.5)
    resp = rec.tail(1200)
    if "Unknown command" in resp[-400:] or "nsh:" in resp[-400:]:
        log("PUSH-FAIL header eaten by the wrong shell")
        return 1

    b64 = base64.b64encode(data).decode()
    aborted = False
    for i in range(0, len(b64), chunk):
        rec.send(b64[i:i + chunk], quiet=pace)
        r = rec.drain(0.1)
        tail = rec.tail(400)
        if "fwpush:" in r or "fwpush:" in tail[-200:]:
            aborted = True
            break
        if "Unknown command: " + b64[i:i + chunk] in r \
                or "command not found" in r:
            aborted = True
            break
    if not aborted:
        rec.send("fwpush_end", quiet=4.0)
    else:
        rec.drain(2.0)
    tail = rec.tail(1200)
    if "fwpush: OK" in tail:
        ok_line = [l for l in tail.splitlines() if "fwpush: OK" in l][-1]
        log("PUSH-OK %s" % ok_line.strip())
        rec.mark("push verdict OK")
        return 0
    log("PUSH-FAIL no board confirmation; tail: %s" % tail[-400:])
    return 1


def quit_agent(rec, label):
    rec.mark("quit %s" % label)
    rec.send("quit", quiet=0.5)
    deadline = time.time() + 10
    while time.time() < deadline:
        rec.drain(0.5)
        if rec.tail(300).rstrip().endswith("nsh>"):
            return True
    return False


def cold(rec, args):
    """The fixed cold-boot sequence. Every step writes to raw."""
    rec.mark("cold start %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    rec.mark("hard reset (RTS)")
    if not rec.link.reset():
        log("RESULT rc=2 no serial port after reset")
        return 2
    ok, wall = wait_nsh(rec, time.time())
    if not ok:
        log("RESULT rc=5 no nsh prompt in %ds" % NSH_WAIT_S)
        return 5
    rec.mark("nsh ready (%.0fs)" % wall)

    ok, _hb = start_buggy_app(rec)
    if not ok:
        return 10

    st = start_agent(rec, "cold")
    if st is None:
        return 7

    if args.push:
        rc = do_push(rec, args.elf, chunk=args.chunk, pace=args.pace)
        if rc != 0:
            log("RESULT rc=8 push gate failed (rc=%d)" % rc)
            return 8

    for i in range(1, args.rounds + 1):
        rc, _data = watch_round(rec, "cold", i)
        if rc != 0:
            return rc
        heap_info(rec, "after-r%d" % i)

    quit_agent(rec, "cold")
    log("COLD-OK rounds=%d push=%s" % (args.rounds, bool(args.push)))
    return 0


def watch(rec, args):
    rec.mark("passive watch %ds" % args.seconds)
    end = time.time() + args.seconds
    n = 0
    while time.time() < end:
        rc, _ = watch_round(rec, "watch", n + 1)
        n += 1
        if rc != 0:
            return rc
    return 0


def cmd(rec, args):
    for c in args.cmds:
        rec.mark("cmd %s" % c)
        rec.send(c, quiet=2.0)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, help="raw log path (append)")
    ap.add_argument("mode", choices=["cold", "watch", "cmd"])
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--push", action="store_true",
                    help="push the hotfix ELF in-process after agent "
                         "start (single-recorder; do NOT run "
                         "push_hotfix.py separately)")
    ap.add_argument("--elf", default=None)
    ap.add_argument("--chunk", type=int, default=252)
    ap.add_argument("--pace", type=float, default=0.02)
    ap.add_argument("--seconds", type=int, default=600)
    ap.add_argument("cmds", nargs="*", help="commands for mode=cmd")
    args = ap.parse_args()

    if args.mode == "cold" and args.push and not args.elf:
        import os
        root = os.path.abspath(os.path.join(
            __file__.rsplit("/", 2)[0], "..", ".."))
        args.elf = os.path.join(root, "apps", "bin", "buggy_app_fixed")

    if not locate_port():
        print("RESULT rc=2 no serial port", flush=True)
        return 2

    rec = Rec(args.raw)
    rec.raw.write("\n===== boardtest %s %s =====\n"
                  % (args.mode, time.strftime("%Y-%m-%d %H:%M:%S")))
    try:
        if args.mode == "cold":
            rc = cold(rec, args)
        elif args.mode == "watch":
            rc = watch(rec, args)
        else:
            rc = cmd(rec, args)
    finally:
        rec.mark("boardtest exit")
        try:
            if rec.link.s:
                rec.link.s.close()
        except Exception:
            pass
    log("RESULT mode=%s rc=%d" % (args.mode, rc))
    return rc


if __name__ == "__main__":
    sys.exit(main())
