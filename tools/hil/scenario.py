#!/usr/bin/env python3
# SiliconLoop HIL: run one diagnostic scenario (A/B/C) on the board and emit a
# one-line JSON verdict.
#
#   A (healthy):    buggy_app &     -> expect END status=ok, no recovery action
#   B (stall):      buggy_app stall & -> expect stalled verdict (heartbeat frozen)
#   C (bug):        buggy_app bug &   -> expect stalled + (after M2/M4) recovery
#
# Usage:
#   python3 scenario.py --scenario A --logfile out.log
#   python3 scenario.py --scenario A --rounds 10 --json out.jsonl
#
# The verdict is parsed from the board log only ("先有日志、再下结论"):
#   PASS requires [trace] END status=ok AND (for A) no recover_task calls.
#   Network/LLM failures are counted separately (net_fail), not as scenario fails.

import argparse
import json
import re
import subprocess
import sys
import time

HERE = __file__.rsplit("/", 1)[0]
SERIAL = [sys.executable, HERE + "/serial_run.py"]

TRACE_RE = re.compile(r"\[trace[^\]]*\] END status=(\w+) iters=(\d+) tools=(\d+)")
STALL_HINTS = ("stalled", "no progress", "heartbeat counter did not", "frozen")

def run_session(logfile, reset, duration, cmds):
    cmd = SERIAL + (["--reset"] if reset else []) + [
        "--logfile", logfile, "--timeout", "40",
        "--duration", str(duration), "--"] + cmds
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 120)
    return r.returncode, r.stdout.strip()

def parse_log(path):
    txt = open(path, "rb").read().decode(errors="replace")
    trace = TRACE_RE.findall(txt)
    status = trace[-1][0] if trace else None
    iters = int(trace[-1][1]) if trace else 0
    net_fail = any(s in txt for s in (
        "llm request failed", "HTTP request failed", "timeout waiting for LLM",
        "network disconnected", "TLS connect failed"))
    recover_called = "recover_task" in txt
    # The verdict comes from the agent's own report (write_file tool call),
    # not from boot noise: match hints only inside report content.
    reports = re.findall(r"write_file args=\{\"path\": \"[^\"]*report\.md\", \"content\": \"(.*?)\"\}", txt, re.S)
    report_txt = " ".join(reports).lower()
    stalled_verdict = any(s in report_txt for s in STALL_HINTS)
    maxfree = None
    m = re.findall(r"maxfree\s+(\d+)", txt)
    if m:
        maxfree = int(m[-1])
    # agent's own free-heap startup line
    m2 = re.search(r"free heap: (\d+)", txt)
    return {
        "status": status, "iters": iters, "net_fail": net_fail,
        "recover_called": recover_called, "stalled_verdict": stalled_verdict,
        "maxfree": maxfree,
        "agent_start_free": int(m2.group(1)) if m2 else None,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True, choices=list("ABC"))
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--logfile", required=True, help="base name; round N gets .rN")
    ap.add_argument("--json", help="append per-round JSON lines here")
    ap.add_argument("--duration", type=int, default=420,
                    help="seconds to keep each session open (heartbeat ~2min)")
    args = ap.parse_args()

    inject = {"A": "buggy_app &", "B": "buggy_app stall &", "C": "buggy_app bug &"}[args.scenario]
    results = []
    for n in range(1, args.rounds + 1):
        lf = f"{args.logfile}.r{n}"
        rc, out = run_session(lf, reset=(n == 1), duration=args.duration,
                              cmds=[inject, "ai_agent"])
        verdict = parse_log(lf)
        verdict.update(round=n, scenario=args.scenario, session_rc=rc)
        if args.scenario == "A":
            verdict["pass"] = (verdict["status"] == "ok"
                               and not verdict["recover_called"])
        elif args.scenario == "B":
            verdict["pass"] = (verdict["stalled_verdict"]
                               and not verdict["net_fail"])
        else:  # C: before M4 lands, a stall verdict alone is partial credit
            verdict["pass"] = verdict["stalled_verdict"]
        results.append(verdict)
        print(json.dumps(verdict), flush=True)
        if args.json:
            with open(args.json, "a") as f:
                f.write(json.dumps(verdict) + "\n")

    ok = sum(1 for r in results if r["pass"])
    net = sum(1 for r in results if r["net_fail"])
    print(json.dumps({"summary": {"scenario": args.scenario,
                                  "rounds": len(results), "pass": ok,
                                  "net_fail": net}}))

if __name__ == "__main__":
    main()
