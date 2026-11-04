#!/usr/bin/env python3
"""Forensic checks on a captured request body (Ghee's 11-03 experiment 1):
- json.loads parseable?
- valid UTF-8 end-to-end (and at every truncation marker)?
- every assistant tool_calls[] entry has function.name + function.arguments
- every tool message has name + tool_call_id + content
"""
import json
import re
import sys

path = sys.argv[1]
raw = open(path, "rb").read()

# the body may be embedded in serial capture noise; find the JSON object
start = raw.find(b'{"model"')
if start < 0:
    print("NO REQUEST BODY FOUND in", path)
    sys.exit(1)
# body ends at the first newline after start (cJSON prints unformatted)
end = raw.find(b"\n", start)
body = raw[start:end if end > 0 else len(raw)]
print("body bytes:", len(body))

try:
    text = body.decode("utf-8")
    print("utf-8 decode: OK")
except UnicodeDecodeError as e:
    print("utf-8 decode: FAIL:", e)
    text = body.decode("utf-8", errors="replace")

# truncation markers: check the byte before each marker is not mid-char
for marker in (b"thinking truncated by SiliconLoop",
               b"truncated by SiliconLoop"):
    idx = 0
    while True:
        idx = body.find(marker, idx)
        if idx < 0:
            break
        window = body[max(0, idx - 12):idx]
        print(f"marker @{idx}: preceding bytes {window[-6:]!r}")
        idx += 1

try:
    req = json.loads(text)
    print("json.loads: OK")
except Exception as e:
    print("json.loads: FAIL:", e)
    # locate the broken region for the record
    for probe in range(0, len(text), 500):
        try:
            json.loads(text[:probe] + "]}]}")  # dummy
        except Exception:
            pass
    sys.exit(2)

msgs = req.get("messages", [])
print(f"messages: {len(msgs)}, tools: {len(req.get('tools', []))}")
bad = 0
for i, m in enumerate(msgs):
    role = m.get("role")
    if role == "assistant" and "tool_calls" in m:
        for j, tc in enumerate(m["tool_calls"]):
            fn = tc.get("function")
            if not fn:
                print(f"  BAD msg[{i}].tool_calls[{j}]: no function key")
                bad += 1
                continue
            if not fn.get("name"):
                print(f"  BAD msg[{i}].tool_calls[{j}].function: no name")
                bad += 1
            if fn.get("arguments") is None:
                print(f"  BAD msg[{i}].tool_calls[{j}].function: no arguments")
                bad += 1
            if not tc.get("id"):
                print(f"  BAD msg[{i}].tool_calls[{j}]: no id")
                bad += 1
    if role == "tool":
        for k in ("tool_call_id", "content", "name"):
            if k not in m:
                print(f"  WARN msg[{i}] tool message missing {k}")
        if "name" in m and m["name"] is None:
            print(f"  BAD msg[{i}] tool message name is null")
            bad += 1
    if role not in ("system", "user", "assistant", "tool"):
        print(f"  BAD msg[{i}]: odd role {role!r}")
        bad += 1

for ti, t in enumerate(req.get("tools", [])):
    fn = t.get("function")
    if not fn or not fn.get("name"):
        print(f"  BAD tools[{ti}]: missing function.name")
        bad += 1

print("structural problems:", bad)
# dump assistant reasoning presence for correlation
for i, m in enumerate(msgs):
    if m.get("role") == "assistant":
        rc = m.get("reasoning_content")
        print(f"  msg[{i}] assistant: reasoning={len(rc) if rc else 0}B "
              f"tool_calls={len(m.get('tool_calls', []))}")
