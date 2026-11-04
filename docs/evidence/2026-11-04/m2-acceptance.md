# M2 验收：板上实测（2026-11-04 凌晨）

固件 = M2+M3 全量（recover_task 工具 + buggy_app 改造 + Skill v2 +
PID 时序修复），构建 2026-11-04 02:48（nuttx.bin 906120 B），
`tools/hil/flash.sh` 烧录（0x2000，Hash 校验通过）。
Kconfig 恢复模式 = 3（auto，Kconfig 默认值，defconfig 未覆盖）。

## 验收结果：三项全部通过 ✅

| 验收项（closed-loop-plan M2） | 结果 | 证据 |
| --- | --- | --- |
| 健康状态下调用工具 100% 被守卫拒绝 | **20/20 全部 refused**（理由 already_healthy） | `m2-guard-healthy.log` |
| stall 状态 L1 后 Δ>0 | **pre_delta=0 → post_delta=50 → recovered** | `m2-recover-l1.log` |
| actions.log 内容正确 | 两份会话各核对（见下） | 两份日志末尾的 cat 输出 |

## 逐项明细

### 1. 健康态守卫拒绝（m2-guard-healthy.log）

`buggy_app &`（正常模式）+ `recover_task test 20`（nsh 专用测试动词，
不经过 LLM）：

```
recover_task test: 20 calls, refused/blocked=20
```

20 次逐条输出均为
`{"result":"refused","reason":"already_healthy"}`——守卫的独立复采样
（两次心跳差 1.5s）每次都测到 Δ>0（pre=50~100），任务健康、一律拒动。
actions.log 记 20 行 `refused_healthy`（pre=post=Δ 实测值，审计口径）。
→ **误处置 0 次**。

### 2. stall 态 L1 恢复（m2-recover-l1.log）

`buggy_app stall &`（消费者停摆 → FIFO 填满 → 心跳冻结）+
`recover_task test 1`：

```
{"level":1,"action":"resume","target":"buggy_app",
 "pre_delta":0,"post_delta":50,"result":"recovered"}
```

守卫链全过：needs_human 无 → 白名单 buggy_app ✓ → 模式 auto ✓ →
冷却/频次 ✓ → 独立复采样 **pre_delta=0**（确属停摆才动手）→
PID 身份核对 ✓ → L1 SIGUSR1 → 复核 post_delta=50 >0 →
复现观察 120s 后再采样仍 >0 → `recovered`。

actions.log 一行（只处置一次）：
`1793732483,buggy_app,resume,pre=0,post=50,recovered`

同窗口内 LLM 心跳诊断也在跑（读 heartbeat.txt 等），未发起第二个
recover_task 调用（全日志 "Executing tool: recover_task" 仅 1 次）。

### 3. PID / mode 文件核验（m2-pid-probe.log，按 Ghee 要求先于 L1 做）

复位后 `buggy_app stall &` + `ai_agent`，回 nsh 核对：

```
ls /data/ai_agent/evidence:  buggy_app.mode  buggy_app.pid  heartbeat.txt
cat buggy_app.pid  ->  5      （ps 中 "buggy_app stall" PID=5，一致）
cat buggy_app.mode ->  stall
```

**PID 时序 bug 已由此验证修复**：修复前 PID/mode 文件在 ai_agent 挂载
/tmpfs 之前写入、静默丢失（L1 会因无 PID 文件直接升级到 L2→needs_human）；
修复后目录就绪即重发身份文件。见 app/hello_app/buggy_app_main.c。

## 内存记录（红线 §4）

| 时刻 | free / maxfree |
| --- | --- |
| agent 启动（本轮新固件） | free heap 141000（M1 验收固件为 142600；-1.6KB 为 recover_task 模块静态量） |
| 探针会话 agent 退出后 | free 272160 / maxfree 202128（关停后回落） |
| 健康态会话 nsh 空闲时 | free 294760 / maxfree 292784 |

诊断进行中的 maxfree 由夜间回归的 `maxfree` 逐轮字段继续统计。

## 已知现象（不影响本验收）

- actions.log 前 14 行时间戳是小整数（板端时钟 NTP 同步前从 0 起跳），
  之后跳到 epoch 值；字段内容（目标/动作/前后 Δ/结果）均正确。
- 优雅关停仍泄漏 TLS 池槽位（"Pool slot 0 still in use at shutdown"，
  已知问题，每轮硬复位规避）。
- 窗口内仍见 emac RX netpkt_alloc 告警（低速散发，未影响本次判定）。
