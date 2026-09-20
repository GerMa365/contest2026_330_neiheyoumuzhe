# SiliconLoop

在 ESP32-P4 上让 AI Agent 自主诊断硬件故障，并为该平台补上了
openvela 缺失的 ELF 动态加载能力。

## 一、作品简介

嵌入式的很多故障在模拟环境里测不出来。`while (!fifo_has_space())`
这样的代码，mock 里谓词恒为真、测试全绿；真机上 FIFO 填满后循环
永不退出，任务再也不前进。这类故障没有崩溃、没有报错，只是"不动了"。

SiliconLoop 做了两件事：

**一、让 Agent 在板上自己发现这类故障**

Agent 每 120 秒被心跳服务唤醒一次，执行七步诊断：读任务清单 → 载入
诊断 Skill → 采样心跳计数 → `ps` → `free` → 再次采样心跳 → 写四段式
报告。两次采样之间由中间两条命令自然拉开十余秒，不依赖 Agent 主动
等待。

判据是心跳增量：涨了就是活的，不涨就是卡死。`ps` 的任务数在两种
状态下完全相同（被测程序的生产者与消费者始终是两个线程），无法据此
区分——这也是我们最初踩过的坑。

连续运行 5.5 小时、162 轮无人干预的回归测试：148 轮完整执行七步
（91%），零缓存空转，8 次失败原因与位置完全一致。

**二、补上 ESP32-P4 的 ELF 动态加载**

该平台此前无法执行编译期之外的程序。定位出两层根因——PMP 将堆区
标记为不可执行、重定位后指令缓存未同步——各用一处改动修复后，
NuttX `elf` 示例的七个测试全部通过，每个测试结束后内存收支归零。

这是平台级的基础能力，不局限于本项目。

**运行环境**

| 项 | 值 |
|---|---|
| 芯片 | ESP32-P4 rev v3.2，单核 RISC-V |
| 堆 | 404 KB |
| 网络 | 以太网 |
| RTC | 无（时钟从 HTTP 响应头校正） |
| LLM | MiMo mimo-v2.5 |

## 二、选题方向

**AI 硬件产品创新。**

价值不在于"把 Agent 跑起来"，而在于让它在 404 KB 堆、无 RTC、单核的
真实设备上稳定工作。这些约束逼出了 Agent 框架每一层的适配：缓存策略、
内存管理、超时机制、时钟校正、工具集裁剪。13 个补丁里有 6 个是为此
而写。

ELF 动态加载是平台层面的附加贡献。

## 三、目录结构

```
contest2026_330_neiheyoumuzhe/
├── README.md                    本文件
├── app/hello_app/
│   ├── buggy_app_main.c         故障注入程序，含 pmp / md 诊断子命令
│   └── hello_app_main.c         比赛方提供的示例，未使用
├── board/contest_board/
│   ├── configs/siliconloop/     完整构建配置
│   ├── src/  include/  scripts/ 板级支持
│   └── Kconfig
├── patches/                     13 个补丁，根因与验证见 patches/README.md
├── skills/
│   └── siliconloop-self-diagnostic.md
│                                自诊断 Skill 的可读版本；实际编进固件的
│                                源在 packages/ai_agent/src/tools/skill_loader.c
├── tools/
│   ├── parse_regression.py      从串口日志逐轮提取指标
│   └── plot_regression.py       绘图
├── docs/
│   ├── product-introduction.md  作品介绍（PDF 版一并提交）
│   ├── technical-deep-dive.md   两个技术成果的定位过程
│   ├── video-script.md          演示视频脚本
│   └── evidence/                板上实测原始日志与统计，见其 README
└── logs/                        AI Coding 日志（仅收尾阶段，见第七节）
```

## 四、补丁清单

13 个补丁分布在 5 个仓库。**没有 0006，编号跳过。**

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

每个补丁的现象、根因、解法、局限与验证记录见
[patches/README.md](patches/README.md)。

## 五、运行方式

分两档。**快速验证**只跑 ELF 加载，不需要 LLM 密钥和网络；
**完整演示**需要配置 LLM。

### 前置：拉取工程

```bash
repo init -u https://github.com/open-vela/contest2026_330_neiheyoumuzhe \
  -b dev-ai-contest-2026 -m contest2026_330_neiheyoumuzhe.xml
repo sync -c -j8
```

以下命令中 `<openvela>` 指工作区根目录，即本仓库的上一级。

### 前置：应用补丁

```bash
# nuttx
cd <openvela>/nuttx
git apply ../contest2026_330_neiheyoumuzhe/patches/0001-esp32p4-support-for-openvela.patch
git apply ../contest2026_330_neiheyoumuzhe/patches/0014-binfmt-elf-sync-icache-after-relocation.patch

# esp-hal-3rdparty（构建时自动拉取）
cd <openvela>/nuttx/arch/risc-v/src/esp32p4/esp-hal-3rdparty
P=../../../../../../contest2026_330_neiheyoumuzhe/patches
git apply $P/0002-esp-hal-openvela-adaptation.patch
git apply $P/0005-esp-hal-eth-link-timer-wdog.patch
git apply $P/0013-esp32p4-pmp-allow-execute-from-heap.patch

# apps
cd <openvela>/apps
git apply ../contest2026_330_neiheyoumuzhe/patches/0003-apps-mbedtls-header-priority.patch

# vendor/openvela
cd <openvela>/vendor/openvela
git apply ../../contest2026_330_neiheyoumuzhe/patches/0004-vendor-board-common-espressif.patch

# packages/ai_agent
cd <openvela>/packages/ai_agent
for p in 0007 0008 0009 0010 0011 0012; do
  git apply ../../contest2026_330_neiheyoumuzhe/patches/$p-*.patch
done
```

打补丁前可先用 `git apply --check` 确认无冲突。

### 前置：编译与烧录

```bash
cd <openvela>
./build.sh vendor/openvela/boards/contest2026_330_board/configs/siliconloop -j8
```

manifest 已把 `board/contest_board` 软链到
`vendor/openvela/boards/contest2026_330_board`，因此 config 路径用软链
后的位置。

```bash
esptool --chip esp32p4 -p /dev/ttyACM0 -b 921600 \
  write_flash 0x2000 nuttx/nuttx.bin
```

**烧录地址必须是 `0x2000`**，写 `0x0` 会覆盖 bootloader。

连接串口：

```bash
picocom -b 115200 --omap delbs /dev/ttyACM0
```

板子复位后 USB 会重新枚举，连接失败时等几秒重试。

### A · 快速验证（不需要 LLM）

```
nsh> elf
```

预期输出七个测试依次执行并通过：errno、hello、signal、struct、
mutex、pthread、task，每个测试结束后打印
`Memory Usage ... Change: 0`。

这条路径验证的是 ELF 动态加载能力，与 Agent 无关。所需的
`CONFIG_ELF`、`CONFIG_LIBC_EXECFUNCS`、`CONFIG_NSH_FILE_APPS`、
`CONFIG_BOARDCTL_ROMDISK`、`CONFIG_EXAMPLES_ELF` 五项已在提供的
defconfig 中开启。

对照日志：
[docs/evidence/2026-09-18/elf-loading-7tests-pass.log](docs/evidence/2026-09-18/elf-loading-7tests-pass.log)

### B · 完整演示（需要 LLM）

**1. 配置密钥**

创建 `packages/ai_agent/include/agent_secrets.h`（该文件在
`.gitignore` 中，不入库）：

```c
#ifndef AGENT_SECRETS_H
#define AGENT_SECRETS_H

#define AGENT_SECRET_LLM_URL "https://your-endpoint/v1"
#define AGENT_SECRET_MODEL   "your-model"
#define AGENT_SECRET_API_KEY "your-key"

#endif
```

改完需重新编译烧录。

**2. 正常状态**

```
nsh> ifconfig            # 确认 eth0 RUNNING
nsh> buggy_app &         # 被测程序，消费者正常工作
nsh> ai_agent
```

等待约两分钟，心跳服务自动触发一轮诊断。预期看到：

```
[heartbeat] Triggered agent check
[agent] Processing message from system:heartbeat
... 七步依次执行 ...
[trace] END status=ok iters=7 tools=7
```

报告落盘在 `/data/ai_agent/evidence/report.md`，判定为 healthy。

**3. 故障状态**

```
nsh> reboot
（重启后）
nsh> buggy_app stall &   # 消费者停止，FIFO 填满后生产者永不退出
nsh> ai_agent
vela> ask diagnose the device
```

预期两次心跳读数相同，Agent 判定任务停止前进。

**4. 诊断工具（可选）**

```
nsh> buggy_app pmp       # 打印 16 条 PMP 配置与地址
nsh> buggy_app md <addr> # 读取指定内存
```

这两个子命令是定位 ELF 加载问题时写的，保留备用。

## 六、向上游的贡献

| 编号 | 内容 | 对应补丁 |
|---|---|---|
| [nuttx#380](https://github.com/open-vela/nuttx/issues/380) | ESP32-P4 上 `esp_hr_timer` 与 HAL `esp_timer` 争用 SYSTIMER alarm 2 / TARGET2，以太网驱动无法初始化 | 0005 |
| [packages_ai_agent#37](https://github.com/open-vela/packages_ai_agent/issues/37) | Skill 与文档硬编码 `/data/agent`，Kconfig 默认值是 `/data/ai_agent`，路径不一致导致服务从未工作 | 0009 |
| [packages_ai_agent#39](https://github.com/open-vela/packages_ai_agent/pull/39) | 上一条的修复 PR，尚未合并 | 0009 |

另有若干真机上发现、尚未提交上游的缺陷，详见 `patches/README.md`，其中几条不限于本项目：

- **TLS 发送超时缺失**：连接池 stale 重连时阻塞写永久等待，agent 主循环无响应
- **定时任务被响应缓存永久短路**：相同提示词命中缓存后任务永远不再运行，日志仍显示 `status=ok`
- **HEARTBEAT.md 与 cron.json 路径不一致**：创建和读取在不同目录，两个服务从未工作过

## 七、AI Coding 使用说明

### AI 参与的环节

| 环节 | 具体做了什么 |
|---|---|
| 根因定位 | ELF 加载失败的两层根因。第一层靠板上 dump PMP 寄存器确认堆区 `X0`；第二层靠板上 dump 内存与主机 `objdump` 逐字节比对，证明内存内容正确、问题在取指路径。沿途排除五个假设，每一条都有依据而非推测。 |
| 数据核对 | 发现 114 轮回归数据里只有 53 轮真正执行了诊断——其余命中 LLM 响应缓存，`llm_ms=0`、`tools=0`，而日志显示 `status=ok`。这个缺陷靠读日志发现不了，只有统计工具调用次数才暴露。修复后重新采集 162 轮。 |
| 缺陷修复 | 13 个补丁中 8 个的修复方案，包括 PMP 权限、指令缓存同步、TLS 发送超时、连接池保质期、心跳路径、缓存策略。 |
| 工具编写 | `parse_regression.py` / `plot_regression.py`，从串口日志提取每轮指标并绘图。 |
| 文档撰写 | patches/README.md（518 行）、证据索引、回归分析、技术文档、本文件。 |

### 关于日志的说明

本项目绝大部分开发使用**网页版 Claude** 完成。按
[大赛手册 Q9](https://github.com/open-vela/docs/blob/dev-ai-contest-2026/zh-cn/contest_2026/ai_coding_log_guide.md)，
网页版不在官方支持的四种工具内，无法自动采集。

`logs/` 目录中的记录仅覆盖**收尾阶段**（README、技术文档、视频脚本），
由 Claude Code 采集。主要开发阶段的对话无法提交。

虽然完整对话不可用，但排查过程本身留在了两处：
[patches/README.md](patches/README.md) 逐个补丁记录了现象、根因、
解法与局限；[docs/evidence/](docs/evidence/) 保留了每个结论对应的
原始日志，包括那些被排除的假设。