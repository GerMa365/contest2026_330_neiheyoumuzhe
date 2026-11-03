#!/usr/bin/env bash
# Host test framework for the SiliconLoop memory guards (Ghee 11-03):
# extracts the REAL firmware code between [TESTABLE] markers and runs
# probe-effectiveness + ASan ownership tests against it. Reused by M2/M3.
set -euo pipefail

AI=/home/w/Project/openvela/packages/ai_agent
CJSON_DIR=/home/w/Project/openvela/apps/netutils/cjson/cJSON
CJSON_INC=/home/w/Project/openvela/apps/include/netutils
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT=/tmp/host-test
mkdir -p "$OUT"

awk '/TESTABLE: alloc-guard begin/,/TESTABLE: alloc-guard end/' \
    "$AI/src/llm/llm_proxy.c" > "$OUT/alloc_guard.inc"
awk '/TESTABLE: req-buf begin/,/TESTABLE: req-buf end/' \
    "$AI/src/llm/llm_proxy.c" > "$OUT/req_buf.inc"
awk '/^cJSON\* build_openai_tools_array/,/^}/' \
    "$AI/src/llm/llm_parse.c" > "$OUT/tools_conv.inc"

for f in alloc_guard.inc req_buf.inc tools_conv.inc; do
    if [ "$(wc -l < "$OUT/$f")" -lt 5 ]; then
        echo "extraction failed: $f"; exit 1
    fi
done

gcc -Wall -Wextra -O1 -I"$CJSON_INC" -I"$OUT" \
    "$HERE/alloc_probe_test.c" "$CJSON_DIR/cJSON.c" -lpthread -lm \
    -o "$OUT/alloc_probe_test"
"$OUT/alloc_probe_test"

gcc -Wall -Wextra -O1 -g -fsanitize=address,undefined -I"$CJSON_INC" -I"$OUT" \
    "$HERE/asround_test.c" "$CJSON_DIR/cJSON.c" -lpthread -lm \
    -o "$OUT/asround_test"
ASAN_OPTIONS=detect_leaks=1 "$OUT/asround_test"

# recover_task guards & escalation: real tool_recover.c, real headers,
# timings shortened via -D for testability
gcc -Wall -Wextra -O1 -g -fsanitize=address,undefined \
    -DCONFIG_EXAMPLES_AI_AGENT_VELA_DATA_DIR='"/tmp/host-test-data"' \
    -DCOOLDOWN_S=1 -DRECUR_OBSERVE_S=2 \
    -I"$HERE/stubs" -I"$AI/src" -I"$CJSON_INC" \
    "$HERE/recover_guard_test.c" "$AI/src/tools/tool_recover.c" \
    "$CJSON_DIR/cJSON.c" -lpthread -lm -o "$OUT/recover_guard_test"
ASAN_OPTIONS=detect_leaks=1 "$OUT/recover_guard_test"

echo "HOST-TEST SUITE: ALL GREEN"
