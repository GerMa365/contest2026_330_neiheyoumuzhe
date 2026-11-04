#!/usr/bin/env bash
#
# SiliconLoop HIL: launch a long job (firmware build, overnight regression)
# so it SURVIVES Claude-session teardown.
#
# Why: a plain background job (& / run_in_background) stays in the
# session's process tree; when the session suspends or its context is
# compacted, the job can be killed mid-flight (2026-11-04: a link step
# died mid-write and left a 0-byte ELF). This wrapper detaches the job
# from the terminal, the session and this shell's process group.
#
# Usage:
#   tools/hil/bg.sh <name> <logfile> <command> [args...]
#
#   <name>     unit name / label (e.g. b2-regression, build-0019)
#   <logfile>  stdout+stderr of the job go here (overwritten)
#
# Preferred path: a transient systemd user unit - outlives the whole
# session regardless of who kills what.
# Fallback (no systemd user bus): setsid + nohup - survives SIGHUP and
# terminal close; this is what carried the 11-04 overnight A/B run.
#
# Check status:  systemctl --user status <name>
# Stop:          systemctl --user stop <name>
# Follow output: tail -f <logfile>
set -euo pipefail

name="${1:?usage: bg.sh <name> <logfile> <command> [args...]}"
log="${2:?usage: bg.sh <name> <logfile> <command> [args...]}"
shift 2
[ "$#" -gt 0 ] || { echo "[bg] no command given" >&2; exit 2; }

# one argv-safe trampoline: $1 = logfile, rest = command
runner=(/bin/bash -c 'l="$1"; shift; exec "$@" >"$l" 2>&1' bash "$log" "$@")

if command -v systemd-run >/dev/null 2>&1; then
    if systemd-run --user --unit="$name" --collect "${runner[@]}" \
            >/dev/null 2>&1; then
        echo "[bg] systemd unit '$name' started (log: $log)"
        echo "[bg]   status: systemctl --user status $name"
        exit 0
    fi
    echo "[bg] systemd-run unavailable, falling back to setsid" >&2
fi

setsid nohup "${runner[@]}" < /dev/null &
disown || true
echo "[bg] setsid job started pid=$! (log: $log)"
