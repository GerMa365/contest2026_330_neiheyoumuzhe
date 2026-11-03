# SiliconLoop 闭环功能开发规划

Nov 1, 2026 · @Ghee

## 一、背景：为什么说项目“没有闭环”

SiliconLoop 目前只完成了 **感知（Sensing）→ 决策（Decision）** 两段，缺少 **执行（Actuation）→ 验证（Verification）**，所以是开环（Open-loop）系统。

现有成果（截至 2026-09-20 提交）：

- **感知**：心跳服务（heartbeat）每 120 秒唤醒 Agent，Agent 采样 `buggy_app` 的心跳计数、`ps`、`free`。
- **决策**：Agent 在 ReAct 循环里调用 LLM，以“两次采样的心跳增量 Δ”为判据，区分 healthy 与 stalled，写出四段式报告 `report.md`。162 轮回归中 148 轮完整走完七步（91%）。
- **平台能力**：补上了 ESP32-P4 的 ELF 动态加载（补丁 0013 + 0014），`elf` 示例七项测试全部通过。

缺口有三处：

1. **没有执行面**：工具白名单（补丁 0008，36 → 11 个）只保留只读命令，Agent 发现故障后无法处置，只能“写报告、等人来”。
2. **没有验证面**：既然不处置，也就没有“处置后故障是否消失”的复核，无法形成反馈（Feedback）。
3. **两个成果互相独立**：ELF 动态加载与 Agent 诊断之间没有任何联系，评委看到的是两件不相关的事。

文档里记录过不加执行能力的原因：第一版 Skill 仅凭进程列表判断，把正常的生产者/消费者两个线程误判为“重复启动”，还建议终止其中一个。若当时有执行权限，就会误杀正常程序。现在心跳增量判据已经过 162 轮验证，**在可靠判据之上增加受控执行**，正是文档自己写下的“安全的顺序”。

本规划的闭环定义：**感知 → 诊断 → 处置 → 复核 → 记录**，每一轮都以复核结果为准，处置失败则升级（Escalation）给人。

## 二、目标与最终效果

最终交付的是一个**故障自愈（Self-healing）闭环**：Agent 在板上发现任务卡死后，按“恢复阶梯”从轻到重逐级处置，每次处置后都用心跳增量复核，恢复不了就升级给人。最高一级处置通过 **ELF 动态加载**运行修复版程序，把项目里两个原本独立的成果连成一条链。

### 答辩现场演示的三个场景

| 场景 | 注入方式 | Agent 的预期行为 | 证明了什么 |
| --- | --- | --- | --- |
| A 正常运行 | `buggy_app &` | 判定 healthy，**不做任何处置** | 不误动作（无假阳性） |
| B 可恢复卡死 | `buggy_app stall &` | 判定 stalled → 一级处置“软恢复”（发信号让消费者线程恢复）→ 复核 Δ>0 → 已恢复 | 最小代价处置 + 复核 |
| C 代码缺陷卡死 | `buggy_app bug &` | 软恢复无效 → 二级“重启任务” → 复核发现**故障复现** → 三级“热修复”：从 `/data` 加载修复版 ELF 替换 → 连续多轮复核 Δ>0 → 已修复 | 区分“暂时恢复”与“根治”，ELF 加载变成 Agent 的处置手段 |

场景 C 是答辩的核心镜头：**重启只能让故障暂时消失，Agent 通过复核发现它会复现，于是升级到热修复，全程无需重新烧录固件**。

### 可量化的验收指标（目标值，最终以回归实测为准）

| 指标 | 定义 | 目标 |
| --- | --- | --- |
| 误处置次数 | 场景 A 中执行了任何处置的轮数 | 0 |
| 检出率 | 场景 B/C 中判定 stalled 的轮数占比 | ≥ 95% |
| 恢复成功率 | 判定 stalled 后最终复核通过的占比 | ≥ 90% |
| 平均恢复时间（MTTR） | 从故障注入到复核通过的时长 | 场景 B ≤ 5 分钟 |
| 第 7 步 OOM 次数 | 写报告时请求体序列化失败 | 50 轮中 0 次 |

### 报告格式升级

`report.md` 从四段式扩展为六段式：观察到的证据、假设、置信度、**采取的处置**、**复核结果**、建议的下一步。另增一份只追加（append-only）的审计日志 `actions.log`，每次处置一行：时间、目标任务、动作、处置前后 Δ、结果。

## 三、总体架构

核心设计原则是 **“LLM 提议、确定性代码裁决”**：LLM 只负责判断“要不要处置、用哪一级”，真正的执行、执行前的再确认、执行后的复核，全部由新增的 C 工具 `recover_task` 完成。这样即使 LLM 误判，守卫也会因为 Δ≠0 拒绝执行。

&#91;embedded content: 闭环架构 · 感知、诊断、处置、复核、记录\]

恢复阶梯每一级执行后都由工具内部复核，失败才升一级；工具只向 LLM 回传一行 JSON 结果，对话历史几乎不增长，避免加重堆碎片。

### 新增与改动的模块

| 模块 | 位置 | 改动内容 |
| --- | --- | --- |
| `recover_task` 工具 | `packages/ai_agent/src/tools/tool_recover.c`（新增，补丁 0015） | 注册为 `TOOL_SEC_SENSITIVE`；入参 `action`（resume / restart / hotfix）与 `target`；内部完成守卫、执行、复核 |
| 工具白名单 | 补丁 0008 | 在现有 11 个工具上加入 `recover_task` |
| 被测程序 `buggy_app` | `app/hello_app/buggy_app_main.c` | 新增 `bug` 模式（启动后一段时间必然卡死，重启只能暂时恢复）；收到 `SIGUSR1` 时恢复消费者线程；启动时写 PID 文件 |
| 修复版程序 | 新目录 `app/buggy_fixed/`，产物 ELF 预置到 `/data/patches/` | FIFO 等待改为带超时与丢弃策略，不再永久阻塞 |
| 诊断 Skill v2 | `skill_loader.c`（Skill 实际编进固件的位置） | 判定 stalled 时调用 `recover_task`，报告改为六段式 |
| 闭环模式开关 | Kconfig | `off` / `dry-run` / `confirm` / `auto` 四档，演示用 `auto`，出问题可退到 `confirm` |
| 审计日志 | `/data/ai_agent/evidence/actions.log` | 只追加，每次处置一行 |

## 四、分阶段里程碑

共七个里程碑，M0–M3 是最小可行闭环（MVP），M4 是把 ELF 动态加载接进闭环的亮点。**上一个里程碑的验收标准没有全部通过，不开始下一个。**

&#91;embedded content: 里程碑排期 · 11 月 1 日至 8 日\]

从 M2 开始，白天开发、夜间用 `regression.sh` 无人值守跑回归，第二天早上按数据决定修什么。

1. **M0 环境复现与 HIL 自动化**
   - 任务：`repo sync` 后按 README 顺序打全 13 个补丁，编译烧录 `siliconloop` 配置；写好 `tools/hil/` 四个脚本。
   - 验收：`elf` 七项测试通过；场景 A 跑通一轮 `status=ok`；`scenario.py` 无人值守连续跑 10 轮并能自动复位；记录基线的空闲堆与最大空闲块。
2. **M1 内存余量**
   - 先测量：在七步的每一步前后打印最大空闲块（largest free block），量出闭环还剩多少余量。
   - 方案 A：启用 PSRAM 作为第二块堆（仓库里已有 `psram_usrheap` 配置可参考），让 `cJSON` 与 TLS 的大块分配落到 PSRAM，ELF 代码段仍留在内部 SRAM。
   - 方案 B：截断工具输出（`ps` 只留关键列）、把旧步骤结果摘要化、报告改由板端按模板拼接。
   - 验收：连续 50 轮第 7 步 OOM 为 0；写出优化前后最大空闲块对比。
3. **M2 执行面 `recover_task`**
   - 任务：实现工具与守卫（白名单、冷却、独立复核 Δ），先做 L1 软恢复和 L2 重启；改造 `buggy_app`（`SIGUSR1`、PID 文件、`bug` 模式）；加一个不经 LLM、直接调用工具的 nsh 测试命令。
   - 验收：健康状态下调用工具 100% 被守卫拒绝；`stall` 状态 L1 后 Δ>0；`actions.log` 内容正确。
4. **M3 复核与恢复阶梯**
   - 任务：处置后两次采样复核；恢复后再观察一个周期做复现检测；升级逻辑；Skill v2 与六段式报告；Kconfig 模式开关。
   - 验收：场景 A、B 各 20 轮，A 误处置 0 次，B 恢复成功率 ≥ 90%。
5. **M4 ELF 热修复**
   - 任务：把修复版程序构建为可加载 ELF 并配好符号表，预置到 `/data/patches/`；L3 = 终止旧任务 → 加载修复版 → 多轮复核。可选：从局域网 HTTP 下载并做 SHA-256 校验。
   - 验收：场景 C 跑 10 轮，至少 8 轮走完 L1 → L2 → L3 并最终复核通过；记录每次加载前后的空闲堆。
6. **M5 闭环回归与证据**
   - 任务：随机混合 A、B、C 场景跑不少于 100 轮，出图（各场景结果分布、MTTR、内存曲线）。**另加一次"不复位长时间连跑"**（≥2 小时、同一 boot 内连续多轮心跳诊断与处置）：scenario.py 每轮硬复位是绕 TLS 泄漏的脚本对策，掩盖了整机长跑下的内存/资源漂移，连跑数据才覆盖真实部署形态。
   - 验收：第二节指标表全部换成实测值，原始日志存入 `docs/evidence/`。
7. **M6 文档、视频与 PPT**
   - 任务：README 新增“闭环”章节和场景 C 的运行方式；`patches/README.md` 补充 0015 起的补丁；录演示视频；导出 Claude Code 日志；PR 合入参赛仓库。
   - 验收：11 月 6 日提交 PPT；在干净副本上照 README 复现一遍场景 B。

## 五、Claude Code 24 小时执行方式

让 Claude Code 自主开发的前提是**硬件在环（Hardware-in-the-Loop, HIL）测试全自动化**：编译、烧录、复位、串口读写、日志判定全部由脚本完成，不需要人按按钮。M0 阶段必须先把这条链打通，否则后面每一步都会卡在“等人插拔”。

### 开工前由你完成的四件事（约 1 小时）

1. **整片 Flash 备份**：`esptool --chip esp32p4 -p /dev/ttyACM0 read_flash 0 ALL backup_full.bin`，存到仓库外。万一板子刷坏，可以原样写回。
2. **确认密钥文件**：`packages/ai_agent/include/agent_secrets.h` 是否还在队友电脑上，LLM 账户余额是否够用（回归测试会跑几百轮）。
3. **新建开发分支**：从参赛仓库的 dev-ai-contest-2026 切出 `git checkout -b feature/closed-loop`，所有改动先进这个分支，验收通过再 PR 合入参赛仓库。
4. **把本规划导出为 Markdown** 放进仓库 `docs/closed-loop-plan.md`，作为 Claude Code 的需求来源。

### 给 Claude Code 的约束（写进仓库根目录 `CLAUDE.md`）

- **范围**：只改本规划列出的模块；新增改动一律以补丁形式落到 `patches/`（编号从 0015 起），不直接改 repo 管理的上游目录而不留补丁。
- **红线**：烧录地址只能是 `0x2000`；`agent_secrets.h` 永不入库；不改 `CONFIG_ESP_SYSTEM_MEMPROT`（已知会导致无法启动）；不删除已有补丁和证据日志。
- **节奏**：一个里程碑一个子分支，每完成一项验收标准就提交一次，提交信息沿用现有风格（`feat(L4): …`、`fix(ai-agent): …`、`docs(evidence): …`）。
- **证据**：每个结论都要有对应的串口原始日志存进 `docs/evidence/<日期>/`，沿用现有的“先有日志、再下结论”的写法。
- **卡住时的规则**：同一个问题连续 3 次修复失败，停下来把现象、已排除的假设、下一步候选写进 `docs/blockers.md`，等人决定，不要无限重试。

### 自动化脚本（M0 交付，放在 `tools/hil/`）

| 脚本 | 作用 |
| --- | --- |
| `build_flash.sh` | 编译 `siliconloop` 配置并以 `0x2000` 烧录，失败即退出 |
| `serial_run.py` | 用 pyserial 复位板子、等待 `nsh>`、按脚本输入命令、把全部输出存成带时间戳的日志 |
| `scenario.py` | 一次跑完一个场景（A/B/C），从日志判定 PASS/FAIL 并输出一行 JSON 指标 |
| `regression.sh` | 按随机顺序循环跑场景，汇总成 CSV，复用现有 `parse_regression.py` / `plot_regression.py` 出图 |

### 你每天的检查点（每天早晚各 20 分钟）

你是答辩人，必须能讲清每个改动。每天让 Claude Code 在 `docs/daily/<日期>.md` 写一份日报：完成了什么、关键决策和理由、遇到的问题、下一步。你读日报，把看不懂的术语记下来，我们在这个 Project 里逐条讲透。

### 顺带解决 AI Coding 日志问题

Claude Code 是大赛官方支持的日志采集工具。这次闭环开发的完整对话可以按《AI Coding 日志归集与提交手册》导出到 `logs/GerMa365/`，补上原来“主要开发阶段日志缺失”的短板。

## 六、风险与兜底

最大的风险不是功能做不出来，而是**做到一半、演示版本反而跑不起来**。所以设两条硬规则：现有 `siliconloop` 配置和固件永远保留为可演示的“保底版本”；**11 月 5 日 18:00 功能冻结（Feature Freeze）**，之后只修缺陷、跑回归、写材料。

| 风险 | 表现 | 应对 | 兜底 |
| --- | --- | --- | --- |
| 堆碎片加剧 | 闭环多了处置步骤，请求体变大，OOM 比原来更频繁 | M1 先做内存余量：优先尝试启用 PSRAM（补丁 0002 已解除 PSRAM 启动阻塞），其次压缩工具输出与对话历史 | 处置与复核由 C 代码完成、只回传一行结果，LLM 轮次基本不增加 |
| ELF 热修复缺少符号表 | 修复版程序依赖的 libc 符号（如 `pthread_create`、`usleep`）在加载时找不到 | 参照 NuttX `elf` 示例的符号表（symtab）做法，只导出修复版需要的符号 | 场景 C 降级为“重启 + 复现检测 + 升级给人”，仍是完整闭环 |
| 误处置 | LLM 在健康状态下调用处置工具 | 执行前由 C 代码独立复核 Δ=0；目标任务白名单只含 `buggy_app` | 配置项切到 `confirm` 模式，处置前需人工输入确认 |
| 网络或 LLM 服务波动 | 请求超时、响应慢（原回归中出现过 200 秒尖峰） | 沿用补丁 0011 的超时与重连机制；回归脚本把网络失败单独统计，不计入功能失败 | 现场演示前录好完整视频备用 |
| 板子卡死需人工复位 | 无人值守回归中断 | `serial_run.py` 通过 RTS/DTR 硬复位；超时自动复位并记录 | 早晚检查点时人工复位 |
| 板子刷坏 | 无法启动 | 只烧 `0x2000` | 用开工前的整片备份写回 |
| Claude Code 跑偏 | 大面积改动上游代码、反复修同一个问题 | `CLAUDE.md` 限定范围；三次失败即停并写 `blockers.md` | 回退到上一个通过验收的提交 |

### 时间线上的取舍顺序

如果进度落后，按这个顺序砍：先放弃 M4 的 HTTP 下载与 SHA-256 校验（修复版 ELF 直接预置在 `/data`），再放弃场景 C 的热修复（保留重启 + 复现检测）。**M1、M2、M3 是最小可行闭环（MVP），不能砍。**

## 七、答辩材料更新

讲述主线从“Agent 能诊断”升级为一句话：**在 404 KB 堆的真实设备上，Agent 发现故障、逐级处置、自我复核，最终通过 ELF 动态加载在线热修复，全程无人干预、无需重新烧录。**

### PPT 新增或改写的页面

1. **问题页**（沿用）：mock 测不出的“不动了”类故障。
2. **闭环总览页**（新）：感知 → 诊断 → 处置 → 复核 → 记录，用第三节的架构图。
3. **安全设计页**（新）：为什么敢让 Agent 动手——“LLM 提议、确定性代码裁决”、目标白名单、恢复阶梯、审计日志。引用第一版误判的故事作为动机。
4. **场景 C 演示页**（新）：重启后复现 → 升级热修复，配串口日志截图或视频。
5. **数据页**（改写）：闭环回归的误处置次数、检出率、恢复成功率、MTTR，加上原 162 轮诊断数据作对比。
6. **平台贡献页**（改写）：ELF 动态加载从“附加贡献”变成“闭环的执行手段”。
7. **局限与展望页**（改写）：PMP 堆区 RWX 的安全代价与正规方案 `up_textheap_memalign()`、修复版 ELF 的签名校验、多任务场景。

### 评委可能追问的问题（开发过程中逐条准备答案）

- 如果 Agent 判断错了，执行了不该执行的动作怎么办？
- 修复版 ELF 是谁写的？Agent 自己生成代码吗？（答：不是。修复程序由开发者预先构建并放进 `/data`，Agent 负责判断何时需要用它。要讲清这个边界。）
- 为什么不直接重启整个板子？
- 把堆区改成可执行，带来了什么安全风险？
- 处置之后为什么还要复核？复核的判据和诊断的判据是同一个，会不会自己骗自己？
- 这套方案能推广到别的任务吗？需要做什么？

上面这些问题，我们在本 Project 里按开发进度一题一题过。

## 八、给 Claude Code 的交接信息

前七节说的是**做什么、为什么做**。Claude Code 还需要知道**东西在哪、怎么跑、哪些只有你能确认**，这一节就补这些。整份文档要先导出为 Markdown，存进仓库 `docs/closed-loop-plan.md`：Claude Code 读不到 claude.ai 上的文档链接。

### 仓库与分支

| 项目 | 地址 | 说明 |
| --- | --- | --- |
| 参赛仓库（评审看这里） | [open-vela/contest2026\_330\_neiheyoumuzhe](https://github.com/open-vela/contest2026_330_neiheyoumuzhe) | 分支 `dev-ai-contest-2026`，9 月 20 日的成果已在其中 |
| 你的 fork | [GerMa365/contest2026\_330\_neiheyoumuzhe](https://github.com/GerMa365/contest2026_330_neiheyoumuzhe) | 完整成果在 `fix/ai-agent-llm-bringup` 分支；fork 的默认分支只到 9 月 9 日，**不要从默认分支开新分支** |
| ai\_agent 上游 | [open-vela/packages\_ai\_agent](https://github.com/open-vela/packages_ai_agent) | 分支 `dev`，补丁 0007–0012 打在这里 |
| 大赛文档 | [大赛总览](https://github.com/open-vela/docs/blob/dev-ai-contest-2026/zh-cn/contest_2026/contest_overview.md) · [代码提交指南](https://github.com/open-vela/docs/blob/dev-ai-contest-2026/zh-cn/contest_2026/code_submission_guide.md) · [AI Coding 日志手册](https://github.com/open-vela/docs/blob/dev-ai-contest-2026/zh-cn/contest_2026/ai_coding_log_guide.md) · [AI 硬件赛道教程](https://github.com/open-vela/docs/blob/dev-ai-contest-2026/zh-cn/contest_2026/ai_hardware/ai_hardware_guide_index.md) | 构建、提交、日志格式以官方文档为准 |

fork 的 `fix/ai-agent-llm-bringup` 与参赛仓库的 `dev-ai-contest-2026` 文件内容完全一致，只有最后一个提交的哈希不同。为了让 PR 干净合入，**新分支从参赛仓库的 `dev-ai-contest-2026` 切出**：`git fetch origin && git checkout -b feature/closed-loop origin/dev-ai-contest-2026`，推送到 fork 后向参赛仓库发 PR。

### Claude Code 开工前必读的仓库文件

- `README.md`：补丁打法、编译烧录命令、两档演示步骤。
- `patches/README.md`：13 个补丁各自的现象、根因、解法、局限；基线提交 nuttx `dd92bcf4`、esp-hal-3rdparty `8d0a8989`。
- `docs/technical-deep-dive.md` 与 `docs/evidence/`：ELF 加载与回归数据的定位过程。
- `app/hello_app/buggy_app_main.c`：被测程序，心跳写在 `/data/ai_agent/evidence/heartbeat.txt`。
- `patches/0008-ai-agent-tool-allowlist.patch`：工具白名单，新工具要加在这里。
- ai\_agent 源码里的 `src/tools/tool_registry.h`（工具注册宏 `REGISTER_TOOL`）、`src/tools/tool_guard.h`（安全等级 `TOOL_SEC_SENSITIVE`）、`src/tools/tool_shell.c`（`kill` 等命令在白名单模式下被禁）、`src/tools/skill_loader.c`（诊断 Skill 的实际源）。

### 硬件与运行环境

| 项目 | 值 |
| --- | --- |
| 开发板 | ESP32-P4 Function EV Board，芯片 rev v3.2，单核 RISC-V |
| 构建配置 | `vendor/openvela/boards/contest2026_330_board/configs/siliconloop` |
| 烧录 | `esptool --chip esp32p4 -p <串口> -b 921600 write_flash 0x2000 nuttx/nuttx.bin`，地址只能是 `0x2000` |
| 串口 | `picocom -b 115200 --omap delbs <串口>`，复位后 USB 会重新枚举 |
| 网络 | 以太网（需网线接路由器） |
| 资源 | 堆 404 KB，无 RTC（时钟由 HTTP 响应头校正） |
| LLM | MiMo `mimo-v2.5`，配置在 `packages/ai_agent/include/agent_secrets.h`（不入库） |

### 只有你能补的信息（开工前逐项填好）

- [ ] **先问组委会**：已确认：截止后新增的提交计入决赛评审，所有改动最终 PR 合入参赛仓库。
- [ ] 队友电脑上 openvela 工作区的绝对路径，以及它是否已经 `repo sync` 过、13 个补丁是否已打上。
- [ ] 电脑的操作系统和串口设备名（Linux 一般是 `/dev/ttyACM0`）。
- [ ] `agent_secrets.h` 是否还在；LLM 账户余额能否支撑几百轮回归。
- [ ] 开发板是否接了网线、能拿到 IP（`ifconfig` 看 `eth0`）。
- [ ] 这台电脑上 Claude Code 是否已安装；GitHub 是否已用 GerMa365 账号登录（能 `git push` 到 fork）。
- [ ] 整片 Flash 是否已备份（第五节第 1 步）。

### 本规划里需要 Claude Code 先验证的假设

以下几点是基于仓库代码推断的方案，不是已验证的事实。M0 阶段先逐条核实，写进 `docs/architecture-notes.md`；**与代码实际情况冲突时以代码为准**，并在 `docs/blockers.md` 记下偏差和替代方案：

1. 启用 PSRAM 作为第二块堆可行，且不影响以太网与 ELF 加载（补丁 0002 只是绕行，有残留映射风险）。
2. 修复版程序能参照 NuttX `elf` 示例的符号表做法，从 `/data` 加载运行。
3. `buggy_app` 可以通过信号恢复消费者线程，Agent 进程有权限向它发信号、终止并重启它。
4. 新工具只回传一行 JSON 时，单轮请求体不超过现有第 7 步的约 12.5 KB。

### 给 Claude Code 的第一条指令（可直接复制）

```markdown
请先完整阅读 docs/closed-loop-plan.md 和 CLAUDE.md，再阅读其中“开工前必读”列出的文件。
本次只做 M0：
1. 核实“需要先验证的假设”四条，结论写入 docs/architecture-notes.md；
2. 复现现有构建与两档演示；
3. 完成 tools/hil/ 下的四个脚本，并无人值守连续跑 10 轮场景 A。
每完成一项验收标准就提交一次，并更新 docs/daily/ 当天的日报。
遇到需要我决定或需要人动手的事（插拔、密钥、账号），写进 docs/blockers.md 后停下来等我。
```

M0 验收通过后，再用同样格式下达 M1，依此类推。**不要一次性把 M0–M6 全部交给它**：每个里程碑结束时由你看日报、确认验收，再放行下一个。
