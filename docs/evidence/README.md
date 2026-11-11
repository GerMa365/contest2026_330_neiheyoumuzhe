# 证据目录

板上实测的原始日志与统计。文档中的每个数字都能在这里找到出处。

## 2026-09-18

### ELF 动态加载

| 文件 | 内容 |
|---|---|
| `elf-loading-7tests-pass.log` | `elf` 示例七个测试全部通过的完整输出（4KB）。补丁 0013 + 0014 的验收记录。 |
| `elf-dynamic-loading-success.log` | 同一轮的详细日志（800KB），开启了 `CONFIG_DEBUG_BINFMT`。包含每一条重定位的地址与结果、加载后代码段前 16 字节的 dump、PMP 寄存器的实际值。定位过程的原始材料。 |

读这两份的顺序：先看小的确认结果，需要追细节时再翻大的。

**关键行**

- `Child: execv was successful!` — 模块内再次 exec 成功
- `Memory Usage End-of-Test: Change: 0` — 加载与卸载的内存收支归零
- `PMP06 cfg=8f R1 W1 X1` — 修复后堆区可执行（修复前为 `cfg=8b X0`）
- `TEXT at 4ff72980: 41 11 05 45 ...` — 内存内容与主机 objdump 逐字节一致

### L3 心跳定时自诊断

| 文件 | 内容 |
|---|---|
| `l3-heartbeat-114rounds.log` | 连续运行 114 次心跳触发的完整日志 |
| `l3-heartbeat-42rounds.log` | 早期的一段，`l3-regression-summary.md` 引用的就是它 |
| `l3-regression-summary.md` | 统计与分析 |
| `regression.png` | 三张图：每轮耗时、单轮内请求体增长、跨轮首次请求大小 |

**注意**：114 轮中只有 53 轮真正执行了诊断。其余轮次命中了
LLM 响应缓存，`llm_ms=0`、`tools=0`，任务并未运行——定时任务
每次发送的提示词相同，一旦有一轮的回复进入缓存，之后每次触发
都直接返回它，而日志仍显示 `status=ok`。

该缺陷已修复（system 通道不查缓存），修复后的数据见
`2026-09-19/`。

## 2026-09-19

### L3 心跳定时自诊断（修复缓存缺陷后）

| 文件 | 内容 |
|---|---|
| `l3-heartbeat-clean-162rounds.log` | 连续 5.5 小时、162 次心跳触发的完整日志 |
| `l3-regression-clean.md` | 统计、与修复前的对比、失败分析 |
| `regression-clean.png` | 三张图，同上一批 |

162 轮全部来自 heartbeat 通道，零缓存命中，148 轮完整执行七步。
八次失败原因与位置完全一致：第 7 步请求体序列化 OOM。

**关键行**

- `BEGIN chat=heartbeat` — 每一轮的起点，无人干预触发
- `END status=ok iters=7 tools=7` — 完整执行七步
- `Heartbeat counter: N → M` — 两次采样的读数，判据所在

## 2026-11-02

决赛闭环开发的起点（M0 基线重建）。elf 七项测试通过，场景 A 健康
状态 10 轮无人值守、误处置 0，内存基线数据在此记录。逐项索引见
`2026-11-02/README.md`。

## 2026-11-03

M1 验收：50 轮场景 A，第 7 步序列化 OOM 从 8/162 降至 **0/50**，
请求体峰值压到 12KB 以下；同时记录了最大空闲块的代价。结论与
逐轮归因见 `2026-11-03/m1-acceptance.md`，另有
`host-mem-guard-tests.log`（主机侧内存守卫单测）与
`dump-analysis.txt`（请求体 dump 分析）。

## 2026-11-04

M2 / M3 板上验收。M2：健康态守卫 20/20 拒绝、stall 态 L1 恢复、
actions.log 正确（`2026-11-04/m2-acceptance.md`）。M3：A×10 误处置 0、
B×10 恢复率 100%、场景 C 阶梯升级（`2026-11-04/m3-acceptance.md`），
夜间回归与 Skill 缺口发现见 `2026-11-04/m3-overnight-01.md`。

## 2026-11-08

M4 板上 smoke 与首轮验收（内存回归判定成立，详见
`2026-11-08/m4-smoke-notes.md`）：fwpush 三例（正例/截断/坏校验和）
全部通过（`m4-smoke2-push-*.log`）；完整心跳轮与 A/C 轮记录
（`m4-smoke3-full-round.log`、`m4-smoke4-san.r1`、`m4-A.r1`、
`m4-C.r1*`、`m4-C.oldfirmware.r1*`）；旧固件对照与烧录 #3 后复验
（agent 启动 free 120,280 → 136,664，见 smoke-notes 修复节）；
刷回答辩版后的健康/卡死复检通过（`m4-flashback-A.r1`、
`m4-flashback-B.r1`）。构建与符号审计单见
`2026-11-08/m4-build-and-symbol-audit.md`（前一提交）。

## 2026-11-12

编译器统一重链（未烧录，详见 `2026-11-12/m4-unify-1340-build-record.md`）：
11-10 编译失败根因为 GCC 13.4.0/14.2.0 混用（blockers 11-11 12:00 条），
全工作区 3,254 个 .o 的 DWARF producer 扫描（`m4-unify-1340-obj-scan.txt`）
确认残留 14.2.0 编译单元仅 3 个（专属仓 app/ 目录），经 Ghee 确认删除后
以 prebuilts 13.4.0 重编（`m4-unify-1340-make.log`、工具链确认
`m4-unify-1340-toolchain-record.txt`）。判据：nuttx ELF 内 14.2.0
编译单元 = 0，通过；sram_seg 139,968 B 与 0024 预期吻合。产物
nuttx.bin 919,652 B（sha256 6a2daa40…，未烧录），System.map 见
`m4-unify-1340-System.map`。

## 复现方式

日志由 picocom 记录：

```bash
picocom -b 115200 --omap delbs --logfile <文件> /dev/ttyACM0
```

固件构建见仓库根目录的构建说明，补丁应用方式见 `patches/README.md`。

## 统计脚本

- `tools/parse_regression.py <日志>` — 逐轮提取状态、耗时、工具调用数、请求体大小，输出到 `/tmp/rounds.json`
- `tools/plot_regression.py` — 读取该 json 绘图

两者需要 matplotlib，装在系统 Python 下即可，与编译固件用的
虚拟环境无关。
