#!/usr/bin/env bash
# SiliconLoop HIL: unattended regression loop.
# Runs scenario.py in a random A/B mix (C added once M4 lands), appends verdicts
# to a JSONL file, and keeps going until N rounds or a stop-file appears.
# Usage: nohup regression.sh <rounds> <scenario-mix> <outdir> &
#        e.g. nohup regression.sh 10 A <outdir> &
set -uo pipefail
ROUNDS="${1:-10}"
MIX="${2:-A}"          # e.g. A, B, AABB, RANDOM
OUTDIR="${3:-.}"
STOPFILE="$OUTDIR/STOP"

HIL="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$OUTDIR"

pick_scenario() {
  case "$MIX" in
    RANDOM) echo "$(( RANDOM % 2 == 0 ? 0 : 1 ))" | sed 's/0/A/;s/1/B/' ;;
    *)      # cycle through the letters in MIX
      local i=$((ROUND % ${#MIX}))
      echo "${MIX:$i:1}" ;;
  esac
}

ROUND=0
while [ "$ROUND" -lt "$ROUNDS" ]; do
  [ -f "$STOPFILE" ] && { echo "stop file seen; ending after $ROUND rounds"; break; }
  SC="$(pick_scenario)"
  ROUND=$((ROUND + 1))
  echo "=== round $ROUND/$ROUNDS scenario $SC $(date '+%F %T') ==="
  /home/w/esp-venv/bin/python3 "$HIL/scenario.py" \
    --scenario "$SC" --logfile "$OUTDIR/scen$SC-$ROUND" \
    --duration 210 --json "$OUTDIR/verdicts.jsonl"
done
echo "regression complete: $ROUND rounds; verdicts in $OUTDIR/verdicts.jsonl"
