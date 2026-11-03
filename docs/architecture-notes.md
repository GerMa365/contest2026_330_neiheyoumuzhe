# 架构核实笔记（M0 起持续更新）

## 2026-11-02 · 工作区补丁状态核实

方法：对每个补丁在目标仓库内 `git apply --check --reverse --ignore-space-change`。

| 补丁 | 目标仓库 | 状态 |
| --- | --- | --- |
| 0002/0005 | esp-hal-3rdparty | 已应用（工作区未提交改动） |
| 0003 | apps | 已应用 |
| 0004 | vendor/openvela | 已应用 |
| 0007–0012 | packages/ai_agent | 已应用 |
| 0013/0014 | nuttx | 已应用 |
| 0001 | nuttx | **内容在位但形态特殊**：已跟踪文件的改动在（M 状态），35 个 diff 里
  的大批新文件以**未跟踪目录**存在（arch/risc-v/src/esp32p4/ 29 个文件、
  include/esp32p4/ 3 个文件）。git apply --reverse 对未跟踪文件无法反向校验，
  属于"已应用、从未提交"的正常表现。 |

结论：**工作区 = 13 个补丁全部在位 + 从未 repo sync 的开发现场**。
红线"禁止 repo sync"与现场状态一致，M0 不需要打任何补丁。

## 待验证假设（规划第八节，逐条补充）

（M0 进行中）

## 2026-11-02 · LLM 配置链与 /data 的持久化真相

发现（对 M4 至关重要）：

1. `agent_main.c:559` 每次开机都会用 `agent_secrets.h` 里的编译期密钥重置
   router slot 0。设计注释写明原因：**/data 是 tmpfs，config.json 活不过重启**。
2. `set_llm` 的"持久化"只在 tmpfs 里，重启即失效——不是持久化机制的缺陷，
   是存储介质本身易失。
3. 对 M4 的影响：**修复版 ELF 放在 /data/patches/ 也活不过重启**。要在断电/
   重启后仍能热修复，必须先把 /data 换成持久文件系统（SMARTFS 已在 config 里，
   SPI flash 16MB，空间够；需要评估挂载点冲突与磨损）。
   这要作为 M4 的前置任务，写进 blockers 让 Ghee 知道。

本次处理（M0 范围内）：按红线"不读取 agent_secrets.h"，用 sed **盲替换**三个
宏（URL/model/API key，值来自 model.md，全程未打印旧值或新值），重新编译烧录。

## 2026-11-02 · 四条技术假设核实（M0，逐条）

### 假设 1：PSRAM 第二堆可行（偏"部分可行，需实验"）
- 现成参考配置 `configs/psram_usrheap`：`CONFIG_ESPRESSIF_SPIRAM=y`、
  `CONFIG_MM_REGIONS=2`、`CONFIG_TESTING_HEAP=y`，且同一板级目录下有效。
- 但 nuttx 主线 esp32p4 板级代码（contest_board/src/esp32p4_bringup.c）**没有**
  任何 SPIRAM/PSRAM 堆注册代码；`psram_usrheap` 只是 xtensa(esp32/s3) 主线板
  的配置名。即：ESP32-P4 的第二堆注册代码**需要自己写**（esp32p4_heap.c 或
  在 bringup 里 mm_addregion）。
- 结论：可行但不是"打开开关就行"。M1 若走方案 A，工作量 = esp-hal PSRAM
  初始化 + mm_addregion + ELF 代码段仍锁内部 SRAM（补丁 0013 的 PMP 区间不变）。
  风险中等。方案 B（压缩）为保底。

### 假设 2：修复版 ELF 参照 elf 示例符号表可行 ✅（代码级已证实）
- `apps/examples/elf/main/test_symtab.c`：手工符号表 g_elf_exports 含
  printf/pthread_*/sleep/usleep/sigaction/kill/task_create 等 34 个符号，
  覆盖 buggy_fixed 全部需求。
- 加载入口 `exec(filename, args, NULL, g_elf_exports, g_elf_nexports)`
  （elf_main.c:388），非标准 exec 支持显式传 symtab。recover_task 的 L3
  可以复用同一表。
- 板上实测 A 档七项全过（m0-elf-7tests.log 与 9-18 基线逐字节一致）。

### 假设 3：信号恢复消费者线程可行 ✅（代码级已证实）
- `buggy_app_main.c`：消费者由 `g_consumer_on` 标志控制（stall 模式置 0）。
- 加一个 SIGUSR1 handler 置回 1 即实现 L1 软恢复；ai_agent 与 buggy_app
  同为用户态任务，`kill()` 已在白名单符号表里，权限不成问题。
- 待 M2 板上实测。

### 假设 4：单行 JSON ≤ 现有 12.5KB 请求体 ✅（设计保证）
- 工具输出缓冲 TOOL_OUTPUT_SIZE=8KB（agent_loop.c:52），单行 JSON 结果
  ≤256B 远小于此。
- v2.6-flash 响应带 reasoning_content，上下文增速比 v2.5 快（r4 中请求体
  7498→10414B），M1 的余量测量必须用新模型重测，不能用旧 12.5KB 数字。

### 附加发现（影响 M4）
- /data 是 tmpfs（agent_main.c:496），重启即空 → 修复版 ELF 无法持久存放，
  set_llm 的"持久化"同样失效。详见 docs/blockers.md。

### 附加发现 2（2026-11-02 11:51，batch v4）：ai_agent 关停泄漏 TLS 池
- 现象：不复位、连续 quit+relaunch agent，第 2 轮起 `ssl_setup ret=0x7f00`
  （mbedtls SSL_ALLOC_FAILED），free heap 从 160KB 跌到 47KB。
- 证据：m0-scenA-batch.r2（batch v4）中
  `Pool slot 0 still in use at shutdown, skipping`。
- 影响：优雅关停路径在修复前不可用；ai_agent 重启必须整机复位。
  M2 的 L2 重启（针对 buggy_app）不受影响，但实现时须验证无同类泄漏。
- 场景脚本对策：scenario.py 每轮硬复位（v5 起）。

## M4 热修复加载空间评估（2026-11-03，M1 系列数据支撑）

**问题**：L3 ELF 热修复要把修复版 ELF 加载进内存执行，空间够吗？

**修复版 ELF 规模**（buggy_app，app/hello_app/buggy_app_main.c）：
- `size apps/bin/buggy_app`：**text 692B / data 28B / bss 16B**，文件 4900B
  （ELF 头 + 段表）。M2 对它的改造（SIGUSR1 恢复、PID 文件、bug 模式）
  预计 text 增加 1-2KB，修复版按 text ≤3KB、文件 ≤8KB 估。
- 加载时需要：文件缓冲 8KB（/data 是 tmpfs，文件本就驻内存）+ 重定位后
  运行镜像 ~4KB + elf 加载器瞬态几 KB。

**B6 之后各阶段最大空闲块实测**（maxfree，单位 B）：
| 数据集 | 固件 | maxfree 范围 |
| --- | --- | --- |
| m0 v5 批量（9 月口径对照） | 基线 | 28,000-44,000 |
| m1-b45-validate2 | B1-B5 | 36,424 |
| m1-50round（7 轮样本） | B1-B5 | 36,896-47,464 |
| m1-b6c-validate | B6 | **18,736**（观察到的最差值） |
| m1-50round-v2 | B6+UTF8 | 采集中 |

**结论：空间够用。** 修复版 ELF 全流程（读文件 + 加载 + 重定位 + 执行）
按 ≤15KB 峰值估，对照最差观测 maxfree 18.7KB 仍有余量；且这是诊断进行中
的瞬时值，热修复发生在诊断结束后的处置阶段，届时堆更宽裕。
- 注意 B6 的 20KB 静态请求缓冲使 agent_start_free 从 159KB 降到 139KB
  （静态区吃掉 20KB），但对 maxfree（最大连续块）影响有限。
- 若 M2 板上实测发现 maxfree 持续 <30KB（D5 触发条件），再评估 PSRAM。
- 存储侧：/data 是 tmpfs，修复包重启即丢（blockers.md 待 SMARTFS 选型），
  与"空间够不够"正交，M4 前必须解决。
