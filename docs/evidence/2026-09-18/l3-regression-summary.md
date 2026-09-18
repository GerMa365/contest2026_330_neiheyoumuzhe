# L3 心跳定时自诊断 · 回归数据

**日期**：2026-09-18
**固件**：nuttx.bin build 2026-09-18 12:30
**板子**：ESP32-P4，404,336 字节堆
**触发方式**：heartbeat 服务每 120 秒自动唤醒，全程无人干预
**原始日志**：`l3-heartbeat-42rounds.log`

## 结果

| 指标 | 数值 |
|---|---|
| 总轮数 | 42 |
| 成功 | 40（95.2%） |
| 失败 | 2（4.8%） |
| 步数一致性 | 39/40 轮为 7 步 7 工具调用 |
| 单轮耗时 | 24s ~ 193s，多数落在 100-190s |

## 每轮执行的七步

1. `read_file` HEARTBEAT.md — 取得本轮任务
2. `read_file` self-diagnostic.md — 载入诊断 Skill
3. `read_file` evidence/heartbeat.txt — 第一次采样
4. `run_shell "ps"` — 任务列表
5. `run_shell "free"` — 堆状态
6. `read_file` evidence/heartbeat.txt — 第二次采样
7. `write_file` evidence/report.md — 四段式报告落盘

两次采样之间由步骤 4、5 自然拉开十余秒，不依赖 Agent 主动等待。

## 失败分析

两次失败均为同一原因，且位置完全一致：

    [agent] Skill in progress — no shortcut
    [llm] OOM: failed to serialize request body
    [trace] iter=6 tool=(none) latency=0ms llm=fail

`latency=0ms` 表明请求未发出，失败发生在构造阶段而非网络传输。
第 7 步的请求体是全流程最大的一次（约 12.5KB），需要一块相应
大小的连续内存供 cJSON 序列化；在 404KB 堆上，此时空闲总量仍
有数十 KB，但已无足够大的连续块。

失败点 100% 集中于此，与网络状况无关——同一轮前六步均正常
完成，且两次失败的耗时分别为 24s 与 107s，差异来自服务器响应
速度而非失败原因本身。

## 请求体增长

单轮内逐步累积：

    iter 0:  7,492 bytes
    iter 1:  8,093
    iter 2: 10,176
    iter 3: 10,641
    iter 4: 11,534
    iter 5: 12,076
    iter 6: 12,502   ← 失败点

跨轮不再累积：连续三轮的 iter 0 均为 7,492 字节。此前心跳使用
固定 chat_id 导致会话历史逐轮增长（7,492 → 7,752 → 8,012），
第三轮即必然失败；改为每轮开始前清空该会话后，该增长消失。

## 判据有效性

同一 Skill、同一流程，在两种状态下给出正确且不同的结论：

| 状态 | 心跳读数 | Agent 判定 |
|---|---|---|
| 正常 | 10900 → 10950 | alive，报告 healthy |
| 故障注入 | 50 → 50 | stall，报告任务停止前进 |

心跳增量是唯一无歧义的判据。`ps` 的任务数在两种状态下相同
（buggy_app 的生产者与消费者始终是两个线程），无法据此区分。
