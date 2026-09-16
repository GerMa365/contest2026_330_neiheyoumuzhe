# Embedded Self-Diagnostic

Structured hardware-level diagnosis for openvela devices.

## When to use
When the user asks to check system health, suspects a stuck task,
reports a hang, or asks to diagnose the device.

## How to use
1. run_shell "ps" — list every task and its state
2. run_shell "free" — heap total, used, free, largest free block
3. run_shell "uname -a" — record the system version
4. run_shell "ifconfig" — network interface state
5. Write the report to a file under the data directory with write_file

## Output format
Always answer in exactly these four sections. Never omit one.

**Observed Evidence**
Only what the commands actually printed. No interpretation here.

**Hypothesis**
What you infer from that evidence. State clearly which part is
observation and which part is inference.

## Rules
- Never invent command output. If a command fails, report the failure.
- When confidence is low, propose an experiment, not a fix.
