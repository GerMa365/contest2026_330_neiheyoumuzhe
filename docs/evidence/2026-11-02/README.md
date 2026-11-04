# 2026-11-02 证据索引（M0）

## 1. elf 七项测试（A 档快速验证）— PASS

- 日志：`m0-elf-7tests.log`
- errno/hello/signal/struct/mutex/pthread/task 全部执行，
  End-of-Test `Change: 0`（内存收支归零）。
- 与 2026-09-18 基线 `elf-loading-7tests-pass.log` 逐项 diff 一致
  （signal 测试中的 "Unexpected signal" 输出为基线固有现象）。

## 2. 场景 A（healthy）无人值守 10 轮 — 10/10 PASS

- 逐轮判定：`scenario-a-10rounds.jsonl`（JSONL，每轮一行）
- 原始串口日志：`m0-scenA-batch.r1 … r10`
- 每轮流程：硬复位 → `buggy_app &` → `ai_agent` → 心跳触发 7 步诊断
  → `END status=ok iters=7 tools=7` → healthy 判定。
- **误处置 0 次**（recover_called=false × 10）——闭环指标基线。
- 内存基线（诊断后 maxfree，字节）：

| 轮 | maxfree | 轮 | maxfree |
| --- | --- | --- | --- |
| r1 | 35,656 | r6 | 30,472 |
| r2 | —* | r7 | 30,232 |
| r3 | 30,408 | r8 | 44,184 |
| r4 | —* | r9 | 30,264 |
| r5 | —* | r10 | 28,184 |

\* 该轮 agent 内部未执行 `free` 工具，无数值；判定不受影响。
范围 28–44KB，10 轮无衰减（每轮硬复位）。

## 3. 附加发现（非验收项，但已记录）

- ai_agent 关停泄漏 TLS 池槽位（详见 `docs/architecture-notes.md`
  "附加发现 2"）：不复位连续重启 agent，第二轮起 mbedtls SSL_ALLOC_FAILED。
  对策：每轮硬复位；M2 实现 L2 重启时须验证无同类泄漏。
- mimo-v2.6-flash 单步延迟方差大（1–111s/步），整轮 LLM 时间 105–384s。
- 复现 OOM 路径：双 agent 并发（脚本缺陷期数据），第 7 步序列化 OOM。
  → M1 方案 B（压缩请求体）对症。

## 4. 运行环境

- 固件：`siliconloop` 配置，nuttx 基线 `dd92bcf4-dirty`（9-20 补丁集 +
  agent_secrets 三宏更新：URL/model/API key，密钥值不入库）
- LLM：mimo-v2.6-flash @ token-plan-cn.xiaomimimo.com（运行时 set_llm +
  编译期引导双保险）
- 每轮时长：复位+启动 ~30s + 心跳 120s + 诊断 105–380s
