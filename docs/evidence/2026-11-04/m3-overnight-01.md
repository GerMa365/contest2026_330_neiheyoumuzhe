# M3 夜间回归第一轮（2026-11-04 03:10–06:05）与缺口发现

命令：`scenario.py --scenario A --rounds 10`（420s 窗口）→
`--scenario B --rounds 10`（600s 窗口），每轮硬复位。
原始日志 `~/claude_work/日志/2026-11-04/m3-overnight/`（20 份 + verdicts.jsonl）。

## Ghee 底线检查：均未触发 ✅

- **OOM = 0**（20 轮合计 0 次序列化 OOM）
- **校验器拦截 = 0**（`request tree incomplete` 0 次）
- → 恢复模式维持 auto，不需要按底线切 dry-run。

## 场景 A（健康，误处置指标）：0/10 ✅

**真实执行口径**（`[tools] Executing tool: recover_task` 计数）：10 轮
全部 **0 次**——模型没有对健康系统提过任何处置。9 轮 status=ok、
1 轮（r7）LLM 服务失败（net_llm，单独计）。

> 判定文件里的 `recover_called=true` 是**解析器误报**：开机日志的
> "[tools] Registered tool: recover_task" 被子串匹配误计（M2 起每轮
> 都有这行）。已修（scenario.py 只认执行行），重解析 20 轮全部
> recover=False。该误报不涉及任何真实处置。

## 场景 B（stall，恢复指标）：恢复 0/3 —— 发现 Skill 缺口 ❌

| 分类 | 轮 | 现象 |
| --- | --- | --- |
| 诊断完成 | B1、B4、B6 | 心跳两次读数一致、**判定 stall 正确**（B1 报告原文 "delta = 0 (stall)"），但**从未调用 recover_task**，报告写完即结束 |
| LLM 服务失败 | B2、B3、B5、B7–B10 | 单步延迟高达 90s+、调用失败/failover 失败（net_llm，单独计，不计功能失败） |

**根因**（代码事实）：Skill 步骤清单停在"5. write_file 报告"，而
报告写入在 agent_loop 里是**终结性本地捷径**（is_terminal_write，
写完直接结束、不再进 LLM）；recover_task 只写在"How to recover"
段落、没有对应步骤——模型走到第 5 步就再无机会调工具。
另：B3 内联摘要把六段式报告漏成了四段（缺 Recovery Action /
Verification）。

**修复**（补丁 0018，059535f）：步骤 5 改为条件处置（判定 stall 才调
recover_task，动作在终结性写入**之前**），报告移到步骤 6；内联摘要
同步并补全六段段名；skills/ 可读版同提交同步。板上验证与第二轮 B
回归见 m3-acceptance.md（续）。

## 解析器修复（d2bdc32，不涉固件）

1. recover_called 只认执行行（修开机注册行误报）；
2. 报告抽取兼容串口日志 ~512B 截断（之前要求闭合引号导致
   stalled_verdict 永远为假）；
3. req_peak 正则不再要求 "bytes)"（日志实为 "bytes, alloc_fail=…"）。

## 内存观察（最大空闲块，红线 §4 继续观察）

诊断期间报告采样：A 轮 11.4–15.6KB（3 轮有采样值）、B 轮 15.6KB
（B1/B4）；请求体峰值 11.3–12.6KB（修复后的解析器统计）。与 M1 验收
（2.2–22.2KB，均值 18.7KB）同量级，**未见进一步劣化**；OOM=0。

## 其他观察

- netpkt_alloc 告警 A 轮合计 119 次、B 轮 123 次（约 11–12 次/轮，
  与 M1 背景噪声同量级），与 net_llm 轮无特定聚集。
- B1 报告："free 15816, maxfree 15552, 910 used blocks, 3 free"——
  碎片化与 M1 一致，未致 OOM。
