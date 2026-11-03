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
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=duration + 120)
    except subprocess.TimeoutExpired as e:
        # serial_run wedged (seen 11-03: a hung LLM call froze the log
        # mid-round). Kill it and treat the round as a session timeout —
        # network/LLM trouble, not a scenario failure.
        print(f"[session timeout after {duration + 120}s: "
              f"{(e.stderr or b'')[-200:]!r}]", flush=True)
        return 124, ""
    if r.returncode != 0:
        # keep serial_run's own diagnosis visible in the scenario log
        print(f"[serial_run rc={r.returncode}] {r.stderr[-400:]}", flush=True)
    return r.returncode, r.stdout.strip()

def parse_log(path):
    try:
        txt = open(path, "rb").read().decode(errors="replace")
    except FileNotFoundError:
        # serial_run died before writing (e.g. port not ready after flash)
        return {
            "status": "no_log", "iters": 0, "net_fail": False,
            "recover_called": False, "stalled_verdict": False,
            "maxfree": None, "oom": 0, "req_peak": None,
            "agent_start_free": None,
        }
    trace = TRACE_RE.findall(txt)
    status = trace[-1][0] if trace else None
    iters = int(trace[-1][1]) if trace else 0
    # Ghee 11-03: separate "window truncated" from real failures. A
    # session whose diagnosis never reached an END (or has no trace at
    # all) was cut by the window or stalled upstream - not a functional
    # failure of the closed loop.
    begins = len(re.findall(r"\[trace[^\]]*\] BEGIN", txt))
    net_fail = any(s in txt for s in (
        "llm request failed", "HTTP request failed", "timeout waiting for LLM",
        "network disconnected", "TLS connect failed"))
    recover_called = "recover_task" in txt
    # The verdict comes from the agent's own report (write_file tool call),
    # not from boot noise: match hints only inside report content.
    reports = re.findall(r"write_file args=\{\"path\": \"[^\"]*report\.md\", \"content\": \"(.*?)\"\}", txt, re.S)
    report_txt = " ".join(reports).lower()
    # A healthy report says "heartbeat healthy (not stalled)" — strip the
    # negated forms first or the substring hints below false-positive on
    # them (m1-regression.r10 did exactly that).
    report_txt = re.sub(r"\bnot\s+(stalled|frozen|stuck)\b", "", report_txt)
    report_txt = re.sub(r"\bno\s+(stall|freeze)\b", "", report_txt)
    stalled_verdict = any(s in report_txt for s in STALL_HINTS)
    maxfree = None
    # Agents word the free output differently across builds ("maxfree N"
    # vs "peak free: N"); accept both so the before/after table has data.
    m = re.findall(r"maxfree\s*:?\s*(\d+)", txt) or \
        re.findall(r"peak free\s*:?\s*(\d+)", txt)
    if m:
        maxfree = int(m[-1])
    # M1 acceptance: count serialization OOMs explicitly (the step-7
    # failure mode) and record the peak request body seen this round.
    oom_count = txt.count("OOM: failed to serialize request body")
    req_sizes = [int(x) for x in
                 re.findall(r"OpenAI API with tools \(model: [^,]+, (\d+) bytes", txt)]
    req_peak = max(req_sizes) if req_sizes else None
    # classify the outcome
    if not trace and begins == 0:
        cause = "no_trace"
    elif not trace:
        cause = "window_truncated"
    elif status == "ok":
        cause = "ok"
    elif status == "timeout" or net_fail or "llm=fail" in txt:
        cause = "net_llm"
    else:
        cause = "functional"
    # agent's own free-heap startup line
    m2 = re.search(r"free heap: (\d+)", txt)
    return {
        "status": status, "iters": iters, "net_fail": net_fail,
        "recover_called": recover_called, "stalled_verdict": stalled_verdict,
        "maxfree": maxfree,
        "oom": oom_count,
        "req_peak": req_peak,
        "cause": cause,
        "agent_start_free": int(m2.group(1)) if m2 else None,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True, choices=list("ABC"))
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--logfile", required=True, help="base name; round N gets .rN")
    ap.add_argument("--json", help="append per-round JSON lines here")
    ap.add_argument("--duration", type=int, default=None,
                    help="session window seconds; default per scenario: "
                         "A=420, B=600, C=900 (closed-loop rounds need "
                         "recovery+verification room)")
    args = ap.parse_args()

    inject = {"A": "buggy_app &", "B": "buggy_app stall &", "C": "buggy_app bug &"}[args.scenario]
    window = args.duration if args.duration else {"A": 420, "B": 600, "C": 900}[args.scenario]
    results = []
    for n in range(1, args.rounds + 1):
        lf = f"{args.logfile}.r{n}"
        # After round 1 the console may still be inside ai_agent's vela> CLI
        # (ai_agent keeps running). "quit" returns to nsh> so the inject and
        # ai_agent commands are parsed by the right shell. The first command
        # after reset is harmless at nsh> (unknown-command noise only).
        # Reset EVERY round: ai_agent shutdown leaks its TLS pool slot
        # ("Pool slot 0 still in use at shutdown"), so heap degrades across
        # in-place restarts (r2 free heap 47KB -> ssl_setup 0x7f00). A board
        # reset per round is also what M0's HIL acceptance demands.
        rc, out = run_session(lf, reset=True, duration=window,
                              cmds=[inject, "ai_agent"])
        verdict = parse_log(lf)
        verdict.update(round=n, scenario=args.scenario, session_rc=rc)
        if args.scenario == "A":
            # M1 acceptance: a serialization OOM anywhere in the session
            # fails the round even if the last heartbeat trace recovered.
            # (stalled_verdict is reported but not a pass gate: a stall
            # wording in a healthy report is a quality signal to review,
            # the hard criterion for M1 is 0 step-7 OOM.)
            verdict["pass"] = (verdict["status"] == "ok"
                               and not verdict["recover_called"]
                               and verdict.get("oom", 0) == 0)
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
    oom = sum(r.get("oom", 0) for r in results)
    misjudge = sum(1 for r in results if r.get("stalled_verdict"))
    causes = {}
    for r in results:
        c = r.get("cause", "?")
        causes[c] = causes.get(c, 0) + 1
    peaks = [r["req_peak"] for r in results if r.get("req_peak")]
    print(json.dumps({"summary": {"scenario": args.scenario,
                                  "rounds": len(results), "pass": ok,
                                  "net_fail": net, "oom": oom,
                                  "misjudge_stall": misjudge,
                                  "cause_counts": causes,
                                  "req_peak_max": max(peaks) if peaks else None}}))

if __name__ == "__main__":
    main()
