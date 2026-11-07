# 补丁总索引

22 个补丁分布在 5 个仓库。**没有 0006，编号跳过。** 各补丁的性质、
根因、解法、局限与验证记录见下文对应小节。

| 补丁 | 目标仓库 | 内容 |
|---|---|---|
| 0001 | `nuttx` | ESP32-P4 芯片支持 |
| 0002 | esp-hal-3rdparty | 跳过 PSRAM MMU 清空 |
| 0003 | `apps` | mbedtls 头文件优先级 |
| 0004 | `vendor/openvela` | 板级公共 Make.defs |
| 0005 | esp-hal-3rdparty | 以太网链路定时器改用 wdog |
| 0007 | `packages/ai_agent` | 主循环：单调时钟、缓存策略、本地工具捷径 |
| 0008 | `packages/ai_agent` | 工具白名单裁剪（36 → 11） |
| 0009 | `packages/ai_agent` | 数据目录宏统一 |
| 0010 | `packages/ai_agent` | 嵌入式内存与超时调优 |
| 0011 | `packages/ai_agent` | TLS 超时、连接池保质期、时钟校正 |
| 0012 | `packages/ai_agent` | heartbeat / cron 路径修复 |
| 0013 | esp-hal-3rdparty | PMP 允许从堆执行 |
| 0014 | `nuttx` | 重定位后同步指令缓存 |
| 0015 | `packages/ai_agent` | 请求体尺寸守卫（工具输出/思考截断、技能内联） |
| 0016 | `packages/ai_agent` | 请求树校验、分配失败计数、16KB 静态缓冲 |
| 0017 | `packages/ai_agent` | recover_task 处置工具（守卫 + 阶梯 + 复核） |
| 0018 | `packages/ai_agent` | 诊断 Skill v2：处置步骤先于报告写入 |
| 0019 | `packages/ai_agent` | recover_task 判定行输出到串口日志 |
| 0020 | `packages/ai_agent` | L2 重启回退内建名（ELF 未部署时仍可重启） |
| 0021 | `packages/ai_agent` | 保底报告（收尾 LLM 失败时由 C 代码写 report.md） |
| 0022 | `packages/ai_agent` | L3 ELF 热修复（exec_spawn + 符号表 + 阶梯第 3 级） |
| 0023 | `packages/ai_agent` | fwpush 串口下发 CLI（修复包经校验落盘 /data/patches） |

0001–0014 为九月阶段（初赛），0015–0021 为决赛新增的闭环功能，
0022–0023 为 M4（L3 热修复）新增（2026-11-08）。

---

# 0001-esp32p4-support-for-openvela.patch

## 这是什么

ESP32-P4 在 openvela `nuttx` 仓库中的支持代码。这些改动位于 repo 管理的
上游公共仓库，无法随队伍仓库提交，因此以补丁形式保存在此。

- 基线提交：`dd92bcf425738734d1b8aed09c2bd4dbe3f2e438`
- 补丁规模：31 个文件，9385 行新增，4 行删除
- HAL 依赖：`ESP_HAL_3RDPARTY_VERSION = 8d0a898910084206721a0892ab093021bca1496a`
  （记录在 `arch/risc-v/src/esp32p4/Make.defs`，构建系统自动拉取，
   584MB 的 HAL 源码**不包含**在本补丁内）

## 什么时候需要用

- 执行过 `repo sync`
- 换了开发机器
- `nuttx` 目录被重置

## 怎么用

```bash
cd <openvela 根目录>/nuttx
git apply --check ../contest2026_330_neiheyoumuzhe/patches/0001-esp32p4-support-for-openvela.patch
git apply ../contest2026_330_neiheyoumuzhe/patches/0001-esp32p4-support-for-openvela.patch
```

`--check` 只检查不修改，先跑它确认无冲突。

## 补丁内容

| 文件 | 改动性质 |
|---|---|
| `arch/risc-v/Kconfig` | 新增 ESP32-P4 芯片选项 |
| `arch/risc-v/src/common/espressif/Kconfig` | if 条件 / choice / CHIP_SERIES 三处注册 P4 |
| `arch/risc-v/src/common/Make.defs` | 芯片层构建规则 |
| `arch/risc-v/src/esp32p4/` | 芯片层源码（来自 Apache NuttX） |
| `arch/risc-v/include/esp32p4/` | 芯片层头文件 |

详细排错过程见 `02_阶段2_3-7_BringUp复盘_01_目录搬迁与Kconfig三层注册.md`。

## 验证记录

在基线提交的干净副本上 `git apply --check` 通过。

副本用以下方式导出（**注意**：repo 管理的仓库无法直接 `git clone`，
其 `.git/objects` 是指向 `.repo/project-objects/` 的符号链接）：

```bash
mkdir -p /tmp/nuttx_patchtest
cd <openvela 根目录>/nuttx
git archive dd92bcf425738734d1b8aed09c2bd4dbe3f2e438 | tar -x -C /tmp/nuttx_patchtest
```

---

# 0002-esp-hal-openvela-adaptation.patch

## 性质：临时绕行（workaround），非功能补充

与 `0001` 不同——`0001` 补充的是缺失的 P4 支持代码，属于长期需要；
本补丁是绕开一个上游缺陷，**上游修复后应当删除**。

## 目标仓库

`nuttx/arch/risc-v/src/esp32p4/esp-hal-3rdparty`（独立 git 仓库，构建时自动拉取）

- 基线提交：`8d0a898910084206721a0892ab093021bca1496a`
- 与 `arch/risc-v/src/esp32p4/Make.defs` 中的 `ESP_HAL_3RDPARTY_VERSION` 一致

## 解决的问题

启用 PSRAM / 以太网 / SPI Flash 任一功能时，系统在启动早期崩溃：

- 现象一：看门狗 10.3 秒周期复位（LP WDT）
- 现象二：停在异常处理中，串口保持连接但无 NSH 提示符
- 两种现象下串口均无任何输出

## 根因

bootloader_init_ext_mem() bootloader_esp32p4.c:162
→ mmu_hal_init()
→ mmu_hal_unmap_all() components/hal/mmu_hal.c:40
→ mmu_ll_unmap_all(MMU_LL_PSRAM_MMU_ID)
→ REG_WRITE(SPI_MEM_S_MMU_ITEM_INDEX_REG, ...)
地址 = DR_REG_PSRAM_MSPI0_BASE + 0x380 = 0x5008e380
→ PMP Store access fault (mcause=0x30000007, mtval=0x5008e380)
→ exception_common → riscv_doirq
→ 中断上下文尚未建立，空指针二次崩溃 (mtval=0xa8)


**PSRAM MSPI 控制器在此时尚未初始化，写其 MMU 寄存器被 PMP 拒绝。**

ESP-IDF 有二级引导程序负责该控制器的初始化；NuttX 在 P4 上使用 Simple Boot
（`CONFIG_ESPRESSIF_SIMPLE_BOOT=y`），ROM 直接跳转至 NuttX，跳过了这一步。

## 相关上游 issue

espressif/esp-idf#16763（IDFGH-15850）
"ESP32-P4 bootloader sometimes bootloops in mmu_ll_unmap_all"

- 状态：Closed，标签 `Resolution: Done`
- 报告者崩溃地址同为 `0x5008e380`，芯片 revision **v1.0**（本项目为 v3.2）
  → **与芯片修订版无关**
- 报告者为间歇性（约 1/10），本项目为每次必现
  → 推测与 ESP-IDF 有二级引导、NuttX 无二级引导的差异有关

## 局限

本补丁直接注释掉 PSRAM MMU 清空，**在使用 PSRAM 时可能导致残留映射**。
正式方案应为：条件编译，或在调用前先初始化 PSRAM MSPI 控制器。

## 怎么用

```bash
cd <nuttx>/arch/risc-v/src/esp32p4/esp-hal-3rdparty
git apply --check ../../../../../../contest2026_330_neiheyoumuzhe/patches/0002-esp-hal-openvela-adaptation.patch
git apply ../../../../../../contest2026_330_neiheyoumuzhe/patches/0002-esp-hal-openvela-adaptation.patch
```

相对路径以实际目录结构为准，建议改用绝对路径。

## 验证记录

应用本补丁后，`spiflash` 配置可正常启动，SmartFS 经 `mksmartfs /dev/smart0`
格式化后可挂载、读写、重启后数据持久。

详见 `03_04R_共同根因_MMU初始化PMP异常.md`。

---

# 0003-apps-mbedtls-header-priority.patch

## 性质：构建修复，长期需要

启用 `CONFIG_CRYPTO_MBEDTLS=y` 的 Espressif 目标都需要。
本项目中即：只要开启 ai_agent，就必须打这个补丁。

## 目标仓库

`apps/`（repo 管理的公共仓库）

## 解决的问题

编译在依赖生成阶段失败，报 7 个 `#error`：

apps/crypto/mbedtls/mbedtls/include/mbedtls/check_config.h:119:2:
error: "MBEDTLS_ECJPAKE_C defined, but not all prerequisites"
check_config.h:313: "MBEDTLS_KEY_EXCHANGE_ECDH_RSA_ENABLED ..."
check_config.h:322: "MBEDTLS_KEY_EXCHANGE_ECDHE_PSK_ENABLED ..."
check_config.h:334: "MBEDTLS_KEY_EXCHANGE_ECDHE_RSA_ENABLED ..."
check_config.h:341: "MBEDTLS_KEY_EXCHANGE_ECDHE_ECDSA_ENABLED ..."
check_config.h:904: "MBEDTLS_SSL_DTLS_CONNECTION_ID_COMPAT ..."
check_config.h:1038: "MBEDTLS_SSL_CONTEXT_SERIALIZATION ..."


触发文件为 esp-hal 的 `bootloader_support/src/bootloader_sha.c`。

## 根因

ESP-IDF（esp-hal-3rdparty）与 NuttX 各自带一份 mbedtls fork，
两者的结构体布局与配置符号集合不同。

`apps/crypto/mbedtls/Make.defs` 用 `${INCDIR_PREFIX}`（展开为 `-I`）
加入 NuttX 那份的头文件路径，使其排在所有 `-I` 路径的最前面，
对**每一个**编译单元生效，包括 esp-hal 自己的源文件。

于是 esp-hal 的文件在 ESP-IDF 配置宏生效的情况下，
命中了 NuttX 的 `check_config.h`，逐项校验全部不匹配。

**注意**：这 7 项并非依赖缺失。`ECP_C` / `ECDH_C` / `ECDSA_C` /
`SSL_PROTO_DTLS` 在 `.config` 中均为 `y`，问题纯粹是头文件串台。

## 解法

`-I` → `-isystem`。NuttX 那份仍可被找到，但优先级降到 ESP-IDF 之后，
esp-hal 源文件转而命中自己那份。

与上游脚本 `packages/ai_agent/fix_esp32s3.sh` 的 fix 1 做法一致
（该脚本为 ESP32-S3 上跑 ai_agent 所写，说明这是 Espressif 平台的共性问题）。

## 怎么用

```bash
cd <openvela 根目录>/apps
git apply --check ../contest2026_330_neiheyoumuzhe/patches/0003-apps-mbedtls-header-priority.patch
git apply ../contest2026_330_neiheyoumuzhe/patches/0003-apps-mbedtls-header-priority.patch
```

## 验证记录

打补丁后，上述 7 个 `#error` 全部消失，编译阶段通过。
ESP32-P4，openvela / NuttX 13.0.0，2026-09-13。

---

# 0004-vendor-board-common-espressif.patch

## 性质：构建修复，长期需要

## 目标仓库

`vendor/openvela/`（repo 管理的公共仓库）

## 解决的问题

`boards/common/src/Makefile` 无条件编译 QEMU 板级辅助文件
（`qemu_weakfunc.c`、`qemu_initialize.c`），这两个文件在 Espressif 目标上不存在。

`arch/risc-v/src/board` 是指向该目录的符号链接，因此每次构建本赛题板子
都会拉入错误的源文件。

## 解法

改为 include 板级公共 `Make.defs`，并在 `CONFIG_ESPRESSIF_SPIFLASH=y` 时
加入 `esp_board_spiflash.c`。

## 怎么用

```bash
cd <openvela 根目录>/vendor/openvela
git apply --check ../../contest2026_330_neiheyoumuzhe/patches/0004-vendor-board-common-espressif.patch
git apply ../../contest2026_330_neiheyoumuzhe/patches/0004-vendor-board-common-espressif.patch
```

## 验证记录

ESP32-P4，openvela / NuttX 13.0.0。该改动自 2026-08-20 起持续生效，
本项目所有成功构建均基于它。

---

# 0005-esp-hal-eth-link-timer-wdog.patch

## 性质：资源冲突绕行，长期需要

在 openvela 上启用 ESP32-P4 以太网必需。

## 目标仓库

`nuttx/arch/risc-v/src/esp32p4/esp-hal-3rdparty`

- 基线提交：`8d0a898910084206721a0892ab093021bca1496a`

## 解决的问题

开启 `CONFIG_ESPRESSIF_EMAC` 后 `esp_eth_driver_install()` 失败：它要
创建一个 esp_timer，而 HAL 的 esp_timer 需要 SYSTIMER alarm 2 /
TARGET2——该资源已被 openvela 的 `ESPRESSIF_HR_TIMER` 占用。把任一方
挪到其他 alarm 均未成功。

## 解法

esp_eth.c 里这个 timer 只做一件事：周期调用 `phy->get_link()` 轮询
网线状态，不在数据通路上。ESP-IDF 自己的头文件也称其为「用于检查链路
状态的内部软件定时器」。改用 NuttX 的 wdog 实现同样的周期回调。

补丁文件开头有完整的英文说明与验证记录。

---

# 0007 ~ 0012：ai_agent 板端适配与缺陷修复

## 性质

`packages/ai_agent` 是上游提供的 Agent 框架，原本面向有 RTC、有充裕
内存、跑在模拟器上的环境。这六个补丁是把它跑在真实 ESP32-P4 上时
逐个暴露并修复的问题。

除 0009 外都不是本项目特有的——任何在资源受限的真机上部署 ai_agent
的项目都会遇到。

## 目标仓库

`packages/ai_agent`（repo 管理的公共仓库）

## 应用方式

```bash
cd <openvela 根目录>/packages/ai_agent
for p in 0007 0008 0009 0010 0011 0012; do
  git apply ../../contest2026_330_neiheyoumuzhe/patches/$p-*.patch
done
```

## 各补丁

| 补丁 | 内容 |
|---|---|
| 0007 | 主循环：单调时钟、缓存策略、本地工具捷径 |
| 0008 | 工具定义白名单裁剪 |
| 0009 | 数据目录宏统一 |
| 0010 | 嵌入式内存与超时调优 |
| 0011 | TLS 发送超时、连接池保质期、时钟校正 |
| 0012 | 心跳与 cron 的文件路径修复 |

---

### 0007-ai-agent-agent-loop-fixes

**看门狗用墙上时钟计时**

超时判断用 `gettimeofday`。板子无 RTC，时钟从 1970 开始，TLS 握手后
一旦校正到当前时间，已耗时会被算成 27 亿毫秒，看门狗立即误判超时。
改用 `CLOCK_MONOTONIC`，共 10 处。

**失败结果进入缓存**

超时后写入的占位文案会被缓存。下一次相同提问直接从缓存返回该错误，
不再触达网络——一次瞬时故障永久污染该提示词。加入 `!watchdog_fired`
条件。

**工具调用结果被缓存**

缓存键是提示词的哈希。纯对话可以缓存，但一旦调用工具，答案就依赖
外部状态：「读取心跳文件」会永远返回第一次的读数。加入
`trace.total_tool_calls == 0` 条件。

**定时任务被缓存永久短路**

定时检查每次发送相同提示词，一旦某轮的回复进入缓存，之后每次触发
都直接返回它：`llm_ms=0`、`tools=0`、任务从不运行，而日志仍显示
`status=ok`。实测 114 次心跳中只有 53 次真正执行。system 通道不再
查询缓存。

**本地工具捷径截断多步推理**

读取本地文件后直接把内容作为最终答复返回，跳过后续 LLM 往返。对
「读这个文件」是合理的优化，但 Skill 执行期间会让流程在第一步就
结束。上游已为 skills 目录打过同类补丁，这里补上 HEARTBEAT.md 与
「Skill 执行期间」两种情形。写文件是终止步骤，仍允许捷径——否则
最后一次复述要多花约 13KB 请求体，正是心跳第 8 轮 OOM 的位置。

---

### 0008-ai-agent-tool-allowlist

36 个工具的 JSON schema 约 10KB。内存紧张时整块分配失败，工具定义
被静默丢弃，模型收到的请求里一个工具都没有，表现为「模型不肯调用
工具」。裁剪为板端实际需要的 11 个，3437 字节。

---

### 0009-ai-agent-data-dir-macro

13 处硬编码 `/data/agent` 与宏 `AGENT_DATA_DIR`（值为
`/data/ai_agent`）并存，读写不在同一位置。统一改用宏。

上游 PR #39 修复同一问题，合并后本补丁可删除。

---

### 0010-ai-agent-embedded-tuning

针对 404KB 堆的参数调整：工具输出池 2→1（省 16KB 峰值）、会话历史
10→4、`CONFIG_IOB_NBUFFERS` 24→64（`netpkt_alloc failed` 由数十条
降为 0）、LLM 超时 60→180 秒、TLS 连接池 2→1（省约 9KB BSS）。

另加：`cJSON_PrintUnformatted` 返回 NULL 时记录日志——此前 OOM 是
完全静默的。

---

### 0011-ai-agent-tls-timeout-and-clock

**连接池 stale 重连必挂死**

`tls_ctx_free()` 首先调用 `mbedtls_ssl_close_notify()`，向已失效的
socket 写数据；而 `SO_SNDTIMEO` 仅在 `CONFIG_AI_AGENT_NET_RPMSG` 下
设置。没有发送超时的阻塞写会永久等待，agent 主循环随之无响应。
改为无条件设置 10 秒发送超时。

**复用被服务器静默关闭的连接**

复用前的 10ms 探测读只能识别对端发送 `close_notify` 的情况。服务器
回收空闲连接时通常不发通知，探测读返回超时而非对端关闭，检查放行；
随后的请求在 TCP 重传中停滞约 100 秒。实测三次为 93.8 / 112.8 / 125
秒。改为记录归还时刻，闲置超过 30 秒直接重建。

**无 RTC，时间从 1970 开始**

从 HTTP 响应头的 `Date` 字段校正系统时钟：准确、零额外往返、不需要
NTP 客户端。注：`strptime` 在本平台有声明无实现，日期解析改用
`sscanf` 加月份查表。

---

### 0012-ai-agent-heartbeat-cron-paths

`HEARTBEAT.md` 与 `cron.json` 创建在 `AGENT_CONFIG_DIR`，而
`heartbeat.c`、`cron_service.c` 读的是上一级的 `AGENT_HEARTBEAT_FILE`
和 `AGENT_CRON_FILE`。文件从不存在于读取方查找的位置：
`heartbeat_has_tasks()` 恒为 false，心跳服务从未触发过；cron 每次
开机打印 "No cron file, starting fresh"。

改用读取方的宏后，该行变为 "Loaded 0 cron jobs"，心跳服务开始工作。

另：每轮心跳开始前清空该会话。心跳使用固定 chat_id，会话历史逐轮
累积，请求体每轮增长约 260 字节，`cJSON_Duplicate` 所需连续块随之
变大，404KB 堆上第三轮即序列化失败——此时仍有 60KB 空闲，是碎片
而非耗尽。

---

# 0013-esp32p4-pmp-allow-execute-from-heap.patch

## 性质：平台能力补充，长期需要

任何想在 ESP32-P4 上使用 NuttX ELF 动态加载的项目都需要。

## 目标仓库

`nuttx/arch/risc-v/src/esp32p4/esp-hal-3rdparty`

- 基线提交：`8d0a898910084206721a0892ab093021bca1496a`

## 解决的问题

加载 ELF 模块后，在其入口点触发异常：

    riscv_exception: EXCEPTION: Instruction access fault.
    MCAUSE: 00000001, EPC: 4ff72840, MTVAL: 4ff72840

此前的每一步都正常：romfs 挂载、ELF 解析、段加载、符号绑定、
数十次重定位写入全部成功，任务也创建了。只有第一条指令取不出来。

## 根因

`esp-hal` 的 `sdkconfig.h` 硬编码了 `CONFIG_ESP_SYSTEM_MEMPROT=1`
（NuttX 的 `.config` 中查不到此项，因此容易漏看），使
`cpu_region_protect.c` 以 `_iram_text_end` 为界把 SRAM 切成两段：

| 范围 | PMP 权限 |
|---|---|
| 0x4ff00000 ~ _iram_text_end | R X |
| _iram_text_end ~ 0x4ffc0000 | R W（无 X） |

堆位于第二段。ELF 模块的代码被加载到堆上，因此可写不可执行。
两条规则均带 L（lock）位，机器模式同样受限，且复位前无法修改。

板上读取 PMP 寄存器确认：

    PMP05 cfg=8d R1 W0 X1 TOR L1 top=4ff49500
    PMP06 cfg=8b R1 W1 X0 TOR L1 top=4ffc0000

失败的入口地址 0x4ff72840 落在 PMP06 内。

## 解法

PMP entry 6 与 9（非缓存别名）由 `RW` 改为 `RWX`。
IRAM/DRAM 的划分保留，固件代码段仍为不可写。

## 局限

数据区变为可执行，牺牲了一部分不可执行内存的防护。
正规方案是实现 `up_textheap_memalign()` 划出专用可执行区，
该移植尚未提供这一支持。

## 验证记录

应用后异常码由 1（取指被拒）变为 2（指令无效）——权限一层已通过，
暴露出下一层问题，见 0014。两者同时应用后 `elf` 示例的七个测试
全部通过。

---

# 0014-binfmt-elf-sync-icache-after-relocation.patch

## 性质：缺陷修复，长期需要

影响所有指令缓存与数据缓存不自动一致的 RISC-V 目标。

## 目标仓库

`nuttx/`

- 基线提交：`dd92bcf425738734d1b8aed09c2bd4dbe3f2e438`

## 解决的问题

解决 0013 后，异常变为：

    riscv_exception: EXCEPTION: Illegal instruction.
    MCAUSE: 00000002, EPC: 4ff72980, MTVAL: 00000000

## 根因

模块代码是经数据通路写入的——每一次重定位都是一条普通 store。
取指走另一条通路，而 ESP32-P4 的内部内存经 L1 缓存访问
（`SOC_CACHE_INTERNAL_MEM_VIA_L1CACHE=1`）且为写回模式，
重定位后的代码仍留在数据缓存中，取指侧从内存读到的是旧字节。

定位方式：在跳转前打印 `textalloc` 处的前 16 字节，与主机上
`objdump` 的结果逐字节比对，完全一致（含正确的 auipc 重定位结果）。
即内存内容无误，问题只可能在取指路径。

`fence.i` 单独不足——它排序的是访存与取指，不负责把写回缓存刷出。
实测仅加 `fence.i` 仍然复现。

## 解法

重定位完成后，对代码段执行缓存写回 + 失效：

    cache_hal_writeback_addr(textalloc, textsize);
    cache_hal_invalidate_addr(textalloc, textsize);

## 局限

`binfmt/` 无法包含厂商 HAL 头文件，函数原型在调用处就地声明。
正规方案是实现 `up_clean_dcache()` / `up_invalidate_icache()`，
该移植尚未提供。

## 验证记录

`elf` 示例七个测试全部通过：errno、hello、signal、struct、mutex、
pthread、task，含模块内再次 exec。每个测试结束后内存收支归零。

日志见 `docs/evidence/2026-09-18/elf-loading-7tests-pass.log`。

---

# 0015-ai-agent-request-size-guard.patch

## 性质：资源约束加固，长期需要

影响所有把工具输出原样放进 LLM 请求的部署；设备堆越小越需要。

## 目标仓库

`packages/ai_agent/`

- 基线：`dev` 分支 + 0007–0012 之后的 `src/core/agent_loop.c`、
  `src/tools/skill_loader.c`、`src/core/context_builder.c`

## 解决的问题

诊断七步中每一步的工具结果（role:"tool" 消息）原样进入后续所有迭代的
请求体。2026-11-02 实测：mimo-v2.6（响应带 reasoning_content，上下文
增长更快）下单轮请求体从 7.5KB 涨到 10.4KB；模拟"双 agent 并发"的
脚本缺陷数据中，第 7 步序列化时精确复现

    [llm] OOM: failed to serialize request body

即 9 月 162 轮回归中 8 次失败的同款 OOM。

## 根因

请求体 = 系统提示(3.0KB) + 工具清单(3.4KB) + 会话历史(最多 4 条，
含整份报告文本) + 本轮累积的全部工具输出。堆剩余 30-46KB 时，
cJSON 序列化峰值叠加 TLS 缓冲，安全余量不足一倍。

## 解法

1. `cap_tool_content()`：每条 role:"tool" 内容超过 1536B 截断并标记
   `[...truncated by SiliconLoop memory guard]`。单工具实测最大
   1626B（skill 文件），ps=481B、free=179B——模型推理只需结果头部。
2. heartbeat 频道的会话历史深度 4→2：诊断是固定七步脚本，旧轮次只
   增加字节不增加信号（人类对话保持 4）。
3. B3 — 心跳每轮都用 read_file 读 1626B 的 self-diagnostic.md，
   文件 + JSON 转义每轮消耗约 2KB。技能是固件常量，故把五步内联进
   skills 摘要（"(steps inline — do NOT read the skill file)"，同时
   压掉原"(read with: read_file ...)"提示，否则模型照提示照样去读），
   摘要 911B→约 1.2KB；`context_builder.c` 的 skills_buf 1024→1536
   防截尾。内联文本含四段报告格式名，报告结构不依赖读文件。
4. B4 — 内联提示不可靠（m1-regression.r1 实测模型两轮心跳都照读
   skill 文件），改在 `tool_files.c` read_file 工具层确定性拦截：
   路径命中 AGENT_SKILLS_DIR 时返回摘要桩（说明 + 文件头 256B），
   全文只在主机侧保留。请求体不再受模型行为影响。
5. B5 — `reasoning_content`（模型思考）在 `add_assistant_message`
   回显进后续每轮请求，m1-b-validate 实测单步 +2.4KB，是 12.5KB
   峰值的主力之一。截断到 256B + 标记；保留字段本体防 Kimi 系 API
   对缺失字段返回 400。
6. 附带修复：snprintf 返回值未钳制可能使 `off` 越过 `size`
   （摘要放在 1KB 栈缓冲上，属潜在栈越界写）。

## 与 0009 的分层说明（skill_loader.c / tool_files.c）

0015 中 skill_loader.c 的改动（B3：诊断步骤内联进 skills 摘要 + 报告
四段格式名 + snprintf 越界钳制）和 tool_files.c 的改动（B4：技能文件
读取返回摘要桩）都以 **0009 应用后的 skill_loader.c/tool_files.c 为基线**
（0009 做了 AGENT_DATA_DIR 宏化改造，本补丁不改 0009 本身）。
0009 先应用、0015 后应用，顺序不可交换。

## 局限

- 截断可能削掉长输出的尾部信息；当前诊断技能用到的输出全部 <1.6KB，
  实际影响为零。若未来工具需要回传大结果，应改为"摘要由工具自己生成"。
- static capped 缓冲区不可重入——add_tool_result_messages 的并行路径
  在 join 之后串行调用它，安全；若改为流水线需加锁。
- **B5 reasoning 回显截断到 256B，可能影响诊断质量**：模型的思考上下文
  被截后，跨步骤的推理链变短。当前场景 A 未见影响（判定只依赖心跳增量），
  但 M3 场景 B（stall 判定）可能需要完整推理，届时实测验证；若质量不足，
  提高 REASONING_ECHO_MAX 或改为"只保留末轮思考"。
- **B4 把技能文件读取改为返回摘要桩**（纯提示 ~150B，不再回传文件内容）：
  模型不再能通过 read_file 获取技能全文。技能步骤已内联在系统提示里，
  诊断流程不受影响；但"让用户查看/编辑技能文件"类交互会被桩截断，
  技能编写场景需在主机侧操作（桩注释里已说明）。

## 验证记录

- 干净副本（dev + 0007–0012）`patch --dry-run -p1` 通过（B1+B2 与 B3
  分两次生成，均对同一基线验证）。
- B1 生效确认：板上日志 `[agent] Tool result capped: 1626 -> 1579 bytes`
  （m1-b-validate.r1）。
- 请求体峰值与 OOM 计数：待 50 轮回归确认（进行中，见日报）。


# 0016-ai-agent-request-tree-guard.patch

## 性质：资源约束加固与发送前校验，长期需要

0015 的续篇（顺序 0015 → 0016）。请求组装路径的分配失败仪表、
发送前请求树校验，顺带把静态序列化缓冲从 20KB 缩到 16KB。

## 目标仓库

`packages/ai_agent/`（agent_loop.c、llm_proxy.c、llm_parse.c）

- 基线：0015 应用之后的树

## 解决的问题

- MiMo 校验器开始拒绝缺 `name` 字段的 tool 消息（"`name` is not
  set"，m1-50round-v2.r1），整轮 400。
- cJSON 吞掉分配失败：malloc 失败时字段静默缺失，堆饥饿时生成
  "缺字段"的请求树（同一类 400），事后无法归因。
- 静态序列化缓冲 20KB 大于所需（实测最大请求 12.7KB），白占
  最大连续空闲块这一瓶颈资源。

## 根因 / 解法

1. tool 消息一律携带 `name`（OpenAI 规范可选、MiMo 必填）；
   llm_parse.c 跳过无名工具定义并告警，坏定义不再出线。
2. cJSON 分配钩子计数 malloc 失败（llm_alloc_fail_count()），
   请求日志带 `alloc_fail=N +M`，失败可归因。
3. 发送前 validate_request_tree()：工具须有 function.name、
   messages 非空且每条有 role；不完整则记
   "request tree incomplete (alloc_fail=…)" 并拒绝发送——
   回归脚本按 tree_incomplete 计数，任何一次出现都是停机判据。
4. s_req_buf 20480 → 16384（16KB，实测峰值 12.7KB）。
5. 不再 cJSON_Duplicate 消息树（深拷贝瞬时堆 ≈ 树本身大小）：
   就地挂接调用方数组、用完摘下归还；tools 数组按 tools_json
   键缓存复用（schema 树约 10KB）。
6. API 非 200 时把请求体转存 evidence/last_request.json 供事后
   定位（须在静态缓冲所有权结束前转存）。

## 局限

- 分配钩子是全局 cJSON 钩子，计数器无锁：单 agent loop 串行下
  安全，若改并行请求路径需加锁。
- tools 缓存以 tools_json 字符串为键，工具集变化时整树重建；
  静态缓冲与缓存均不可重入。
- last_request.json 只在失败时写、每次覆盖，不是历史档案。

## 验证记录

- 干净副本（0015 应用后）`patch --dry-run -p1` 通过。
- M1 50 轮验收（docs/evidence/2026-11-03/m1-acceptance.md，含附1
  的 16KB 核实与时代表）：OOM=0，请求峰值 12.7KB < 16KB。
- "request tree incomplete" 在 M1 50 轮与 11-04 夜间 20 轮
  （m3-overnight-01.md）均为 0 次。


# 0017-ai-agent-recover-task.patch

## 性质：闭环执行面（M2+M3），合并 m2-wip 时落地

0016 的续篇（顺序 0015 → 0016 → 0017）。recover_task 是处置动作的
唯一入口（红线 7）；"LLM 提议，确定性代码裁决"。

## 目标仓库

`packages/ai_agent/`（tool_recover.c/h 新增，tool_registry.c/h、Kconfig、
skill_loader.c 增改）

- 基线：0016 应用之后的树

## 解决的问题

场景 B/C 的处置执行面：stall 判定后需要确定性恢复（L1 软恢复 →
L2 重启）与升级给人的出口；诊断报告需要记录处置与复核（六段式）。

## 根因 / 设计

- 守卫（全在 C 代码）：needs_human 锁存 → 目标白名单（仅 buggy_app）→
  冷却 120s + 每小时 6 次上限 → Kconfig 模式（off/dry-run/confirm/auto）
  → 独立重新采样确认 Δ=0（健康任务永不触碰）。
- 阶梯：L1 SIGUSR1 唤醒消费者 → L2 SIGTERM+原样重启（代码缺陷会复现，
  阶梯继续走）→ **L3 热修复随 M4 调整为"升级给人"**。
- 处置后复核：两次采样 Δ>0 = 恢复；**复现检测（M3）**：恢复后再观察
  一个心跳周期，Δ=0 视为复发，升一级或升级给人。
- 返回一行 JSON ≤256B（recovered/recurred/needs_human/refused/
  needs_confirm/dry_run）；actions.log 只追加审计。

## 局限

- L2/L3 各阻塞 agent loop 数秒（等待+复核+观察窗口），演示可接受；
  并行诊断受影响时改异步处置（M5 前议）。
- 复现观察窗口 120s（一个心跳周期）在工具内 sleep，主机测试用
  -DRECUR_OBSERVE_S 缩短。
- hotfix 入参返回 m4_deferred，M4 恢复后启用。
- **PID 复用防护**：发出 SIGUSR1/SIGTERM 前核对 /proc/<pid>/status 的
  Name 确为 buggy_app 家族；PID 文件过期且号码被复用时拒绝执行并记
  actions.log（pid_mismatch）。
- **防并发**：处置进行中（s_recovering）的再次调用返回 refused:busy；
  串行 agent loop 下心跳诊断自然排队等待处置结束。
- **阻塞时长**：一次调用最长约 4.3 分钟（L1 复发 + L2 复发 + 两次
  120s 复现观察）；典型恢复路径约 2 分钟。工具执行发生在 LLM 调用
  之间，不触发 LLM 超时（AGENT_LLM_TIMEOUT_SEC=180 只约束 llm 调用）。
- **解锁**：`recover_task reset`（nsh/vela CLI）清 needs_human 锁存与
  冷却状态，无需复位，供答辩现场连续演示。
- **reset/test 仅限人工 CLI**：两者只存在于 vela> CLI 的命令循环
  （非 NSH 内建命令，run_shell 触达不到）；工具入参 action 传
  reset/test 一律拒绝（cli_only），host-test G 场景覆盖。

## 验证记录

- 干净副本（0015+0016 应用后）patch --dry-run 通过。
- 主机测试 tools/host-test/recover_guard_test.c（ASan/UBSan 零报告）：
  健康态 20 次调用全部被守卫拒绝；stall 态 L1 恢复 + 复现观察通过；
  L1 无效 → L2 失败 → needs_human；恢复后观察窗内复发 → recurred。

# 0018-ai-agent-skill-v2-recover-step.patch

## 性质：闭环诊断 Skill 修正（M3），合并 m2-wip 后的增量补丁

0017 的续篇（顺序 0015 → 0016 → 0017 → 0018），只改 skill_loader.c
（该文件已在 0017 中改过，按规范新增增量补丁，不改旧补丁）。

## 目标仓库

`packages/ai_agent/`

## 基线提交

0017 应用后的 skill_loader.c（与 0017 同一上游基线，增量导出）。

## 解决的问题

场景 B（stall 注入）里模型正确判定 stall 却从不调用 recover_task：
11-04 夜间 3 轮完成诊断的 B 轮全部如此，恢复 0/3。

## 根因

Skill 的步骤清单停在"5. write_file 报告"，recover_task 只出现在
"How to recover"段落里、没有对应步骤；而报告写入在 agent_loop 里
是**终结性本地捷径**（is_terminal_write，写完直接结束本轮、不再进
LLM）——模型按步骤走到第 5 步写完报告，循环就结束了，永远没有机会
在之后调工具。内联摘要（B3）还把六段式报告压成了四段。

## 解法

- 步骤 5 改为条件处置：判定 stall 才调 recover_task（action=resume、
  target=buggy_app），记录一行 JSON 结果；健康或心跳文件缺失则跳过。
  报告写作移到步骤 6，**动作发生在终结性写入之前**。
- 内联摘要同步新步骤，并补全六段式报告的段名（Recovery Action /
  Verification 之前被漏掉）。
- skills/siliconloop-self-diagnostic.md 同提交同步（双份一致规则）。

## 局限

- 内联摘要增长约 230B 至约 1.47KB，skills_buf 1536B 内但偏紧；超长时
  既有钳制保证不越界。若后续再加内容需同步扩 buffer。
- 模型遵循度仍是概率性的（LLM 提议面）；裁决面（守卫/阶梯/复核）在
  C 代码里不受影响。
- 报告文本在串口日志里截断到约 512B（日志框架限制），scenario.py 的
  判定已改为基于工具执行行与工具返回行（短行不截断）。

## 验证记录

- 干净副本（0017 应用后）`patch --dry-run -p1` 通过（2026-11-04）。
- 板上验证见 docs/evidence/2026-11-04/：B 轮模型按新步骤调用
  recover_task 并拿到 {"result":"recovered"}（L1 + 复现观察）。

# 0019-ai-agent-recover-verdict-log.patch

## 性质：证据链补齐（M3），增量补丁

0017 的续篇（应用顺序 0015 → 0016 → 0017 → 0018 → 0019），只改
tool_recover.c（0017 新增该文件，0018 未触碰）。

## 目标仓库

`packages/ai_agent/`

## 基线提交

0017 应用后的 tool_recover.c。

## 解决的问题

工具结果在串口日志里只记字节数（"Tool recover_task result: 101
bytes"）：恢复轮的判定 JSON 只存在于 LLM 会话与 /data 的
actions.log（tmpfs，掉电即失），轮次证据链断裂，scenario.py 无法
从日志判定 recovered。

## 根因

agent 只把工具结果回传给 LLM，日志框架打印的是长度不是内容。
判定行本身是设计好的公开输出（一行 JSON ≤256B、无敏感信息），
应当随日志留档。

## 解法

tool_recover_execute 拆出 _inner 保持原逻辑不动，外层包装在返回前
syslog 一行 `[recover] verdict {...}`。串口日志从此永久携带每轮
判定（recovered / recurred / needs_human / refused / dry_run /
needs_confirm），scenario.py 的 `"result":"recovered"` 计数有据可依。

## 局限

- 解析按子串匹配判定行；若日志分级过滤变化需保证 LOG_INFO 可见。
- actions.log 仍是权威审计，本补丁只是把同一行镜像到串口日志。

## 验证记录

- 干净副本（0017 应用后）`patch --dry-run -p1` 通过（2026-11-04）。
- 板上验证：B 场景重跑各轮日志含 verdict 行，见
  docs/evidence/2026-11-04/m3-acceptance.md。

# 0020-ai-agent-l2-spawn-builtin-fallback.patch

## 性质：缺陷修复（M3 场景 C 暴露），增量补丁

0017 的续篇（应用顺序 0015 → 0016 → 0017 → 0018 → 0019 → 0020），只改
tool_recover.c（0017 新增该文件，0018 未触碰）。

## 目标仓库

`packages/ai_agent/`

## 基线提交

0019 应用后的 tool_recover.c。

## 解决的问题

L2 重启阶梯的 posix_spawn 永远失败：目标路径
`/data/ai_agent/bin/buggy_app` 从未存在。buggy_app 是 NuttX 内建应用
（builtin），没有 ELF 部署到 /data；/data 是 tmpfs 每次上电清空，
即便部署过也活不过复位。于是"重启任务"这一级永远走不到，
bug 模式无法演示 L1 无效 → L2 重启 → 复现 → 升级给人。

## 根因

L2 按 m2-wip-design 的部署步骤设计（`apps/bin/buggy_app` → 板上
`/data/ai_agent/bin/`，L2 重启用），但该部署步骤从未纳入自动化
流程；设计文档也没有覆盖"部署缺失时怎么办"。

## 解法

respawn() 先按原设计 posix_spawn 部署路径；失败则回退用内建注册名
"buggy_app" 再试一次。两条路都经 posix_spawn，argv 保留 mode 参数，
重启后的进程复现同一 workload。

## 局限

- 内建名回退依赖 builtin binfmt 按名查找（上游 NuttX 支持；若
  openvela 有差异会在板测暴露）。
- 持久化的修复版 ELF 部署仍属 M4（/data tmpfs 问题见
  docs/m4-design.md），本补丁只保证 L2 在无部署时也能重启。

## 验证记录

- 干净副本全链 0007 → … → 0020 `git apply` 通过（2026-11-04）。
- 板上验证：场景 C（bug 模式）重跑，数据见
  docs/evidence/2026-11-04/m3-acceptance.md 的场景 C 一节。

# 0021-ai-agent-fallback-report.patch

## 性质：能力补充（M3 保底报告），增量补丁

0019 的续篇（应用顺序 0015 → 0016 → 0017 → 0018 → 0019 → 0020 → 0021），
改 tool_recover.c/.h（0017 新增、0019/0020 续改）、agent_loop.c 与
tool_files.c 各一处挂钩。

## 目标仓库

`packages/ai_agent/`

## 基线提交

0020 应用后的树（0007 → … → 0020 全链 `git apply` 干净副本）。

## 解决的问题

处置（recover_task 阶梯）已经执行、但随后"写报告的 LLM 调用"失败时，
report.md 完全缺失。尾部 LLM 失败在低堆时稳定复现（场景 C 每轮必现、
场景 B 约 1/10），报告是六段式交付物，缺报告等于该轮证据链断裂。

## 根因

报告内容只由 LLM 生成；request body 序列化在低空闲块下分配失败后，
写报告这一步没有任何确定性兜底。判定行（0019）当时已经携带了报告
所需的全部字段，却没有被利用。

## 解法

判定返回前把报告预渲染进 1024 字节静态缓冲（零堆分配）并置位；仅当
"本会话阶梯执行过 ∧ 本会话 report.md 尚未由 write_file 写成功 ∧ 会话
以 LLM 终态失败结束"时才 open/write/close 落盘，一次恢复最多写一份。
write_file 成功写 report.md、或新会话开始都会撤防。内容 = 判定字段
（level/action/pre_delta/post_delta/result）+ 目标名 + 时间 + 一行规则
结论（L1 后恢复 = 临时停顿；L2 后恢复 = 任务已替换；阶梯走完 = 疑似
代码缺陷需查源码）+ 标记 "LLM unavailable: fallback report"。

## 局限

- 报告模板是英文固定文案，不含采样明细（设计简化：不做采样捕获）。
- 仅覆盖"recover_task 已执行"这一路径；LLM 一开始就失败时无报告
  （该路径本就没有处置发生，符合"只在处置后兜底"的设计）。
- 静态缓冲 1024 字节；字段超长会被 snprintf 截断（判定行 ≤256B 的
  约束保证了正常使用不会触顶）。

## 验证记录

- host-test：tools/host-test/fallback_report_test.c 六用例（C 型写出、
  B 型结论、健康不写、正常报告优先、会话边界撤防、一次性 + 重新武装），
  ASan/UBSan 零报告（2026-11-04）。
- 干净副本全链 0007 → … → 0021 `patch --dry-run -p1` 通过（2026-11-04）。
- 板上：场景 C 三轮保底报告 3/3 写出，见 docs/evidence/2026-11-04/
  m3-fallback/ 与 m3-acceptance.md。

# 闭环验证数据汇总（2026-11-04）

0015–0021 构成决赛闭环（请求体守卫 → 树校验 → recover_task 处置
工具 → Skill 处置步骤 → 判定行日志 → L2 重启回退 → 保底报告）。板上回归数据
（原件 docs/evidence/2026-11-04/）：

| 场景 | 轮数 | 判据 | 结果 | 主要验证的补丁 |
| --- | --- | --- | --- | --- |
| A 健康 | 10 | 误处置 = 0 | 0/10 ✅ | 0017 守卫（独立复采样拒绝） |
| B 卡死 | 10（夜间）+ 10（重跑） | 恢复率 ≥90% | 重跑 10/10、9/9 = 100% ✅ | 0018（处置步骤前置）、0019（判定行） |
| C 代码缺陷 | 5 | 阶梯走完并升级 needs_human | 见 m3-acceptance.md 场景 C 一节 | 0017 阶梯、0020（L2 重启回退） |

底线（Ghee 口径）：

- 序列化 OOM：**0**（35 轮合计，0015/0016 的目的）
- 发送前校验器拦截（request tree incomplete）：**0**（0016 的目的）
- 最大空闲块：诊断期间 10.0–15.6KB，低于 M0/M1 基线但底线口径
  （OOM/拦截）持续为零，未进一步劣化。

→ 提交版本默认闭环模式保持 auto（README 第五节写明降级条件与
切换方法）。

# 0022-ai-agent-l3-hotfix.patch

## 性质：能力补充（M4 L3 热修复），增量补丁

0019/0020/0021 的续篇（应用顺序 0007 → … → 0021 → 0022 → 0023）。
恢复阶梯从两级扩为三级：L1 resume → L2 restart → **L3 hotfix**（停掉
故障任务，用 exec_spawn 从 /data/patches/buggy_app_fixed 加载修复版
ELF 顶替）。本补丁同时修正 0017 的导出遗漏：Makefile/CMakeLists.txt
当时漏加了 `src/tools/tool_recover.c` 的 CSRCS 行（工作树有、补丁无，
干净基线应用 0017 后 tool_recover.c 不会被编译），此处一并带上。

## 目标仓库

`packages/ai_agent/`

## 基线提交

0021 应用后的树（0007 → … → 0021 全链 `git apply` 干净副本，含
0017 遗漏修正的上下文）。

## 解决的问题

L2 重启对"代码缺陷"类故障无效：重启只是把同一份带 bug 的二进制再跑
一遍，故障必然复现（场景 C 的核心现象）。阶梯需要能真正替换故障代码
的一级——把修复版（与 buggy_app 仅一处行为差异：drain 路径无条件
释放槽位）作为可重定位 ELF 在运行时加载。

## 根因

exec 家族在本配置下的可用面：`CONFIG_LIBC_EXECFUNCS=y` 但
`CONFIG_EXECFUNCS_HAVE_SYMTAB is not set`——posix_spawn 依赖的 OS
内置符号表不存在，无法加载可重定位 ELF；`exec()`（替换映像变体）会
把 ai_agent 自己换掉。NuttX binfmt 提供的、支持调用方传入符号表的
接口是 `exec_spawn()`（binfmt.h，独立任务启动、返回 pid、不替换
调用者），调用者需自备 `struct symtab_s` 表。

## 解法

- `tool_recover.c`：新增 `rung_hotfix()`（L3）：payload 存在性与大小
  守卫（52B–16KB）→ `stop_task()`（SIGTERM + 轮询退出）→
  `exec_spawn(HOTFIX_ELF_PATH, argv, NULL, g_hotfix_exports,
  g_hotfix_nexports, NULL, &attr)`（attr 带与原注册一致的 priority 50 /
  stacksize 4096，argv 透传原 mode）→ 6s 后复采样。阶梯循环上限 2→3；
  `action:"hotfix"` 映射 level 2；`level_name` 扩为
  {resume, restart, hotfix}；保底报告结论行补 L3 分支。判定 JSON 仍
  ≤256B；LLM 侧无任何变化（Skill 只提 resume，阶梯在 C 代码内自动
  爬升——LLM 不可直达 L3，符合"LLM 提议、C 裁决"）。
- `hotfix_exports.c/.h`（新增）：L3 专用导出表，内容 = 修复版 ELF 的
  `nm -u` 审计清单（2026-11-08，16 符号：fclose fopen fprintf fputs
  getpid printf pthread_create pthread_mutex_lock pthread_mutex_unlock
  puts sched_getparam sched_setparam signal sleep strcmp usleep），
  逐项精确匹配，不多导出。payload 源码变更时须重跑审计并同步本表。
- `agent_main.c`：Phase 0 补 `mkdir /data/ai_agent/patches`。
- host 测试：`SILILOOP_HOST_TEST` 编译期剥离 exec_spawn 路径（glibc 无
  此 API 也无 spawnattr.priority），host 上 L3 视为 rung 失败、阶梯
  走到 needs_human——L3 的真实验证在板上（验收表第 2–5 项）。

## 局限

- payload 驻留 tmpfs，复位即失，每轮由 fwpush（0023）重推；Flash
  持久化是赛后工作（SmartFS 方向）。
- 符号表是静态白名单：payload 新增导入而表未同步 → 加载期符号解析
  失败 → 阶梯升级 needs_human（安全方向的失败）。
- FNV-1a 校验只防传输误码，不防篡改；payload 签名校验是赛后工作。
- ELF 代码段落在内部 SRAM（0013 已放开的 PMP 范围）；PSRAM 执行是
  独立实验方向，与 M4 不绑定。

## 验证记录

- 干净副本全链 0007 → … → 0021 → 0022 → 0023 `git apply` 通过，
  逐文件与工作树 `diff` 一致（2026-11-08）。
- host 测试（ASan/UBSan，recover_guard_test + fallback_report_test +
  asround_test）ALL GREEN（2026-11-08）。
- 符号审计：`nm -u apps/bin/buggy_app_fixed` 16 项 = 导出表 16 项
  （2026-11-08，见 docs/evidence/2026-11-08/ 符号核对单）。
- 板上验收：待跑（验收表 smoke → C×5 → A×10 → 失败路径 → 持续运行
  → B×3），证据入 docs/evidence/2026-11-08/。

# 0023-ai-agent-hotfix-push-cli.patch

## 性质：能力补充（M4 修复包下发通道），增量补丁

只改 `src/channels/nsh_commands.c`：新增 `fwpush` CLI 命令。与 0022
配套，应用顺序在其后。

## 目标仓库

`packages/ai_agent/`

## 基线提交

0022 应用后的 nsh_commands.c。

## 解决的问题

修复版 ELF 需要进入板上的 /data/patches/（tmpfs）。备选方案里
ROMFS 编译期内嵌等于"出厂自带补丁"，违背热修复命题（m4-design 第三节
选项 D，仅作兜底）；串口下发让"构建 → 推包 → Agent 发现 → 热替换"
全链路可见，且 /data 为 tmpfs、不碰 Flash。

## 根因

板上没有任何现成的大文件传输通道（nsh 无 rz/sz；LLM 工具通道按设计
不运载数据文件）。

## 解法

`vela> fwpush <total_bytes> <fnv1a_hex>` 进入接收态，读 base64 行
（每行解码后 ≤512B，行缓冲 1024B），`fwpush_end` 结束；总量硬上限
16KB，超限/坏块/短读一律删除半成品拒用。落盘前**回读全文件重算
FNV-1a-32**（板端与主机各算一遍），校验一致才把文件留在
/data/patches/buggy_app_fixed——损坏传输在源头被拦下（这同时是验收
表"坏包"路径的前半段）。FNV-1a 只防传输误码，不防篡改（签名是赛后
工作）；命令仅人工 CLI 可达，LLM 工具面无此入口。

## 局限

- 921600 波特下 ~6.4KB payload 传输约 10s 量级，可接受；更大队长不
  适合本通道（16KB 硬上限）。
- 无重传：传输中断即整包作废，重新执行 fwpush 即可。

## 验证记录

- 干净副本链上 `git apply` 通过、与工作树一致（2026-11-08）。
- 板上：smoke 测试正常包过验、截断/篡改包被拒（验收表第 1 项，待跑）。
