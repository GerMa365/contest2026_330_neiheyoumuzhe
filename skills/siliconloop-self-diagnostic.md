# Embedded Self-Diagnostic

Structured hardware-level diagnosis for openvela devices.

> 可读版本：内容以固件 `skill_loader.c` 的 `BUILTIN_SELF_DIAGNOSTIC`
> 为准（0009 + 0015-B3/B4 改动之后）。**修改固件里的 Skill 内容时，
> 必须在同一提交里同步更新本文件。**

## When to use
When the user asks to diagnose the device, check system health,
reports a hang, or suspects a stuck task.

## How to use
Follow these steps in order. One tool call per step.
1. read_file /data/ai_agent/evidence/heartbeat.txt - record it
2. run_shell "ps" - every task and its state
3. run_shell "free" - heap total, used, free
4. read_file /data/ai_agent/evidence/heartbeat.txt again
5. write_file the report to /data/ai_agent/evidence/report.md

## How to judge
The heartbeat counter is the primary signal.
- Value increased between step 1 and step 4: the monitored task
  is alive. Report healthy.
- Value identical: the task stopped making progress. This is a
  stall. Report it as the main finding.
- File missing: the task never started.

Task and thread counts in ps are NOT evidence of a fault on
their own. A process with worker threads shows several entries
with the same name; that is normal.

## Output format
Answer in exactly these four sections. Never omit one.
Maximum 3 sentences per section. Be concise.

**Observed Evidence**
Both heartbeat values and what the commands printed. No
interpretation.

**Hypothesis**
What you infer. Say which part is observation, which is
inference.

**Confidence**
High, medium or low, with the reason for that rating.

**Proposed Test or Fix**
A concrete next step. Not a vague suggestion.

## Rules
- Never invent command output. Report failures as failures.
- Call exactly one tool per step. Never batch tool calls.
- When confidence is low, propose an experiment, not a fix.

## 固件侧的行为差异（B3/B4，读文件时注意）

- 技能步骤同时**内联在系统提示**的 Skills 摘要里（B3），心跳诊断可以
  不读本文件直接执行。
- read_file 读取本文件（或任何 `skills/` 下的文件）只会返回**摘要桩**
  （B4 内存守卫），全文以本文件为准。
