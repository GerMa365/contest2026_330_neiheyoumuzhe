#!/usr/bin/env python3
# SiliconLoop HIL: logcheck - raw-log integrity checker.
#
# 2026-11-24 lesson (cc-report-1124-fail / tech-debt plan 2.2): three
# attach-too-late incidents left criterion lines uncaptured and the gaps
# were only found by hand. This checker formalizes the invariants a raw
# log must satisfy and prints every violation in RED so a gap cannot
# hide inside a "PASS" summary:
#
#   MISSING_END     a [trace:ID] BEGIN chat=... has no matching END
#   ITER_GAP        a trace's iter numbers skip (0,1,3...) or repeat
#   LLM_NO_RESULT   "[llm] OpenAI API with tools" with no "[llm] Response"
#                   line before the next iteration's request
#   NO_MEMPROBE     a trace whose rounds ran with 0 memprobe lines
#   PROBE_MISSING   round-level: END seen but not one memprobe line in it
#   ORPHAN_ITER     iter=N line with no BEGIN seen before it (attach-
#                   too-late signature - the round started off-log)
#
# 2026-11-25 additions (tech-debt batch 2, H1+H2):
#   H1 ROUND_WINDOW  a "# host: [boardtest] round N start" marker whose
#                    window does not contain exactly one BEGIN/END pair.
#                    Catches a whole round that never reached the raw
#                    log (A-r2) — invisible to every trace-line check.
#   H2 cold-start segmentation: trace ids repeat across cold boots
#      (unseeded 20-bit rand, see G2 in cc-report-1125-b2), so a trace
#      id matched across a "# host: [boardtest] cold start" marker is a
#      DIFFERENT trace, not the same one. The log is split into cold-
#      start segments before grouping by trace id; ids repeat freely
#      across segments without triggering DUPLICATE_*.
#
# Replay (offline, no board):
#   python3 logcheck.py docs/evidence/2026-11-24/m4-3a-boardtest-a.raw
#
# Exit code: 0 = no violations, 1 = violations found (so CI/scripts can
# gate on it), 2 = file unreadable.
import re
import sys

RED = "\033[31m"
GREEN = "\033[32m"
OFF = "\033[0m"

RE_BEGIN = re.compile(r"\[trace:([0-9a-f]+)\] BEGIN chat=(\w+)")
RE_END = re.compile(
    r"\[trace:([0-9a-f]+)\] END status=(\w+) iters=(\d+) tools=(\d+)")
RE_ITER = re.compile(r"\[trace:([0-9a-f]+)\] iter=(\d+) tool=(\w+)")
RE_LLM_REQ = re.compile(r"\[llm\] OpenAI API with tools")
RE_LLM_RESP = re.compile(r"\[llm\] Response:")
RE_MEMPROBE = re.compile(r"\[sloop-memprobe\] peak pre-write")
RE_COLD_START = re.compile(r"# host: cold start ")
RE_ROUND_START = re.compile(
    r"# host: \[boardtest\] round (\d+) start (\S+)")
RE_ROUND_END = re.compile(
    r"# host: \[boardtest\] round (\d+) end (\S+)")


def check(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        print("cannot read %s: %s" % (path, e))
        return 2

    findings = []

    # H2: split the log into cold-start segments BEFORE grouping by
    # trace id. Trace ids repeat across cold boots (unseeded rand, G2),
    # so a [boardtest] round start marker also closes the segment it
    # belongs to implicitly? No — rounds within one cold boot share the
    # id space legitimately; only a new "# host: cold start" begins a
    # new segment.
    segments = []   # (name, [ (line_no, text) ])
    seg_lines = []
    seg_name = "pre-cold"
    for i, line in enumerate(lines, 1):
        if RE_COLD_START.search(line):
            if seg_lines:
                segments.append((seg_name, seg_lines))
            seg_name = "cold@line%d" % i
            seg_lines = []
        seg_lines.append((i, line))
    if seg_lines:
        segments.append((seg_name, seg_lines))

    for seg_name, seg in segments:
        findings.extend(_check_segment(seg_name, seg))
    return findings


def _check_segment(seg_name, seg):
    """Check one cold-start segment. traces are local to the segment
    (H2): the same id in a later segment is a different trace."""
    traces = {}   # id -> {"begin": line_no, "iters": [(n, line)], "end": line, "probes": n}
    pending_req = None   # line_no of last LLM request awaiting a Response
    findings = []
    # H1 bookkeeping: round idx -> {"start": ln, "begin": n, "end": n,
    #                              "close": ln or None, "label": str}
    rounds = {}

    def t(tid):
        return traces.setdefault(tid, {"begin": None, "iters": [],
                                       "end": None, "probes": 0,
                                       "resp_seen": True})

    for ln_no, line in seg:
        rm = RE_ROUND_START.search(line)
        if rm:
            rounds.setdefault(int(rm.group(1)), {})["start"] = ln_no
            rounds[int(rm.group(1))]["label"] = rm.group(2)
            rounds[int(rm.group(1))].setdefault("begin", 0)
            rounds[int(rm.group(1))].setdefault("end", 0)
            continue
        rm = RE_ROUND_END.search(line)
        if rm and int(rm.group(1)) in rounds \
                and "close" not in rounds[int(rm.group(1))]:
            rounds[int(rm.group(1))]["close"] = ln_no
            continue
        m = RE_BEGIN.search(line)
        if m:
            tid = m.group(1)
            if t(tid)["begin"] is not None:
                findings.append(("DUPLICATE_BEGIN", ln_no, line.strip(),
                                 "trace %s has a second BEGIN" % tid))
            t(tid)["begin"] = ln_no
            for ridx in rounds:
                r = rounds[ridx]
                if "close" not in r and ln_no > r.get("start", 0):
                    r["begin"] += 1
            continue
        m = RE_END.search(line)
        if m:
            tt = t(m.group(1))
            if tt["end"] is not None:
                findings.append(("DUPLICATE_END", ln_no, line.strip(),
                                 "trace %s has a second END" % m.group(1)))
            tt["end"] = ln_no
            for ridx in rounds:
                r = rounds[ridx]
                if "close" not in r and ln_no > r.get("start", 0):
                    r["end"] += 1
            continue
        m = RE_ITER.search(line)
        if m:
            tt = t(m.group(1))
            tt["iters"].append((int(m.group(2)), ln_no))
            if not tt["resp_seen"]:
                findings.append(
                    ("LLM_NO_RESULT", ln_no, line.strip(),
                     "iter=%d of trace %s: the LLM request before it has "
                     "no [llm] Response line" % (int(m.group(2)),
                                                 m.group(1))))
                tt["resp_seen"] = True
            continue
        if RE_LLM_REQ.search(line):
            pending_req = ln_no
            tid = _owner_trace(traces, ln_no)
            if tid is None:
                findings.append(("ORPHAN_LLM_REQ", ln_no, line.strip(),
                                 "LLM request outside any BEGIN/END window"))
            else:
                traces[tid]["resp_seen"] = False
            continue
        if RE_LLM_RESP.search(line):
            tid = _owner_trace(traces, ln_no)
            if tid is not None:
                traces[tid]["resp_seen"] = True
            continue
        if RE_MEMPROBE.search(line):
            tid = _owner_trace(traces, ln_no)
            if tid is None:
                findings.append(("ORPHAN_MEMPROBE", ln_no, line.strip(),
                                 "memprobe outside any trace window"))
            else:
                traces[tid]["probes"] += 1

    for tid, tt in sorted(traces.items(), key=lambda kv: kv[1]["begin"] or 0):
        if tt["begin"] is not None and tt["end"] is None:
            findings.append(("MISSING_END", tt["begin"],
                             "trace %s BEGIN at line %d" % (tid, tt["begin"]),
                             "no END line found in the whole log"))
        if tt["begin"] is None and tt["end"] is not None:
            findings.append(("ORPHAN_END", tt["end"],
                             "trace %s END at line %d" % (tid, tt["end"]),
                             "BEGIN was never captured (attach-too-late)"))
        ns = [n for n, _ in tt["iters"]]
        if ns:
            expect = list(range(ns[0], ns[0] + len(ns)))
            if ns != expect:
                gaps = [e for e in expect if e not in ns]
                findings.append(("ITER_GAP", tt["iters"][0][1],
                                 "trace %s iters=%s" % (tid, ns),
                                 "missing iter numbers: %s"
                                 % sorted(set(gaps))))
        if tt["end"] is not None and tt["probes"] == 0:
            findings.append(("NO_MEMPROBE", tt["end"],
                             "trace %s ended without a single memprobe line"
                             % tid,
                             "the round's memory evidence is missing"))

    if pending_req is not None and not any(
            f[0] == "LLM_NO_RESULT" for f in findings
            if f[1] >= pending_req):
        findings.append(("TRAILING_LLM_REQ", pending_req,
                         "log ends with an unanswered LLM request",
                         "the log was cut off mid-round"))

    # H1: every [boardtest] round-start window must contain exactly one
    # BEGIN and one END. A window with 0/0 means the whole round never
    # reached the raw log; 2+ means interleaved duplicates.
    for ridx in sorted(rounds):
        r = rounds[ridx]
        label = r.get("label", "?")
        if "start" not in r:
            continue
        if "close" not in r:
            findings.append(("ROUND_WINDOW", r["start"],
                             "[boardtest] round %d (%s) start at line %d"
                             % (ridx, label, r["start"]),
                             "no round-end marker: the driver died "
                             "mid-round or the marker was lost"))
            continue
        if r.get("begin", 0) != 1 or r.get("end", 0) != 1:
            findings.append(("ROUND_WINDOW", r["start"],
                             "[boardtest] round %d (%s) start line %d .. "
                             "end line %d"
                             % (ridx, label, r["start"], r["close"]),
                             "expected exactly 1 BEGIN + 1 END in the "
                             "window, saw %d + %d (0/0 = the round never "
                             "reached the raw log)"
                             % (r.get("begin", 0), r.get("end", 0))))

    return findings


def _owner_trace(traces, line_no):
    """Best-effort: the trace whose begin<=line and (end is None or
    end>=line). Raw logs interleave at most two traces (console echo vs
    round), so first match is the practical owner."""
    best = None
    for tid, tt in traces.items():
        if tt["begin"] is not None and tt["begin"] <= line_no \
                and (tt["end"] is None or tt["end"] >= line_no):
            if best is None or tt["begin"] > traces[best]["begin"]:
                best = tid
    return best


def main():
    if len(sys.argv) < 2:
        print("usage: logcheck.py <raw.log> [more.raw ...]")
        return 2
    total = 0
    for path in sys.argv[1:]:
        findings = check(path)
        if findings == 2:
            return 2
        print("\n== %s ==" % path)
        if not findings:
            print(GREEN + "OK: all invariants hold "
                  "(BEGIN/END pairs, iter continuity, LLM results, "
                  "memprobe presence)" + OFF)
            continue
        for kind, ln, ctx, detail in findings:
            total += 1
            print(RED + "[%s] line %d: %s" % (kind, ln, ctx) + OFF)
            print("        %s" % detail)
    print("\nTOTAL violations: %d" % total)
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
