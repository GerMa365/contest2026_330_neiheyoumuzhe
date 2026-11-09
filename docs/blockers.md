# Blockers

## 2026-11-02 09:20 · /data 是 tmpfs，M4 的 ELF 修复包无法持久存放
- 现象：`agent_main.c:496` 把 /data 挂成 tmpfs（"for simulation" 注释），
  重启后 config.json、report.md、heartbeat.txt 全部消失；`set_llm` 的
  持久化也随之失效（每次开机由 agent_secrets.h 重新引导）。
- 已尝试 / 已排除的假设：
  - 尝试运行时 set_llm：当次开机有效，重启即回退（m0-reboot-llmcheck.log）。
  - 已排除"持久化代码缺失"：llm_router_set_backend 正常写 config_store。
- 我建议的下一步（选项与风险）：
  1. 把 /data 挂到 SPI flash 上的 SMARTFS 分区（config 已有 SMARTFS 支持，
     16MB flash 有空间）。风险：需要选好分区偏移避开 0xd8000 弱单元区
     （见 claude_work/日志/2026-11-02/01-flash-backup.md）；首次格式化会清掉
     该区现有内容；需要在 bringup 或 agent_main.c Phase 0 改挂载逻辑。
  2. 维持 tmpfs，M4 的修复版 ELF 每次开机由脚本经串口推入（HIL 已能做）。
     风险：现场演示断电即丢，答辩时"重启后热修复仍在"的叙事减弱；
     但所有验收日志仍可自动完成。
- 需要 Ghee 做什么：选择 1 或 2（我建议 1，M4 之前完成；0xd8604 附近的
  弱单元用分区边界避开即可）。

## 2026-11-03 15:20 · API 400：请求树字段静默丢失（B6 时代构建）
- 现象：MiMo 偶发 400 "name/function is not set"；dump+回放证明是我们 body
  缺字段（tools[].function 内容 / tool_calls[].function 被丢）。"Invalid
  JSON" 那类是 UTF-8 切坏（已修）。
- 已排除：转换代码（host 无辜）、B5 reasoning 截断（b5off 仍 400）、
  name 修补（非原因）、服务端无端收紧（校验一直都在）。
- 疑因：B6 静态缓冲使堆 159K→139K，cJSON 分配失败静默丢字段（工作假设）；
  alloc 探针 9+ 请求 alloc_fail=0 未捕捉到损坏事件，**机制未定论**。
- 已做：发送前树校验（永久，不完整不发+记 alloc_fail）、工具数组缓存、
  messages 挂接替代深拷贝、静态缓冲 20K→16K。
- 需要：M5 前用 50 轮验收回归数据复盘（jsonl + "request tree incomplete"
  日志）；若仍复现，按"内存被写坏"方向查（重点：.bss 邻接、工具输出池）。

## 2026-11-03 22:45 · 最大空闲块低于 M0 基线（红线 9.6 汇报）
- 现象：M1 验收 50 轮（docs/evidence/2026-11-03/m1-acceptance.md）最大
  空闲块 2.2–22.2KB、均值 18.7KB，明显低于 M0 基线 28–44KB。M1 的两条
  验收标准（50 轮第 7 步 OOM=0 ✅、优化前后对比已写 ✅）均已满足，
  本条只汇报资源劣化，不阻塞 M1 打标签。
- 已尝试 / 已排除的假设：
  - 已排除"泄漏累积"：每轮硬复位后 agent_start_free 稳定 142600，
    无逐轮衰减；劣化是开机即有的静态占用，不是运行中流失。
  - 疑因（已量化，2026-11-04 核实）：**静态序列化缓冲实际是 16KB**
    （`llm_proxy.c:134` `s_req_buf[16384]`，B6 时代的 20KB 已在"减压
    三项"里缩到 16KB）。启动空闲堆三档对照：B6-20KB 版 138.5–140.4KB、
    本次验收 16KB 版 142.6KB、B6 之前 159.4–161.0KB——20KB→16KB 的
    收缩已在验收固件里生效（回升约 2–4KB）；剩下的 17–18KB 差距是
    B 系列全部静态占用（16KB 缓冲 + 工具数组缓存等小缓冲）。换来的
    收益：序列化零堆分配，第 7 步 OOM 从 8/162 归零。
- 我建议的下一步（选项与风险）：
  1. 先按既定计划跑 M2/M3 板上实测，记录处置阶段（诊断结束后的堆更宽裕
     时刻）的最大空闲块；若持续 <30KB（D5 触发条件），再评估 PSRAM 方案 A
     （P4 需自写堆注册，风险与工时都大）。风险：夜间回归期间内存吃紧可能
     再引 OOM——但 50 轮零 OOM 说明当前余量可用。
  2. 立即收缩静态缓冲 16K→8K 试压。风险：请求体峰值 11.9KB 已接近该值，
     可能重新触发序列化失败，得不偿失。
  3. 立即上 PSRAM 方案 A。风险：截止 11-04 18:00 前完不成的概率高。
- 需要 Ghee 做什么：知悉该劣化与取舍（OOM 归零 vs 空闲块变小）；若你认为
  最大空闲块是硬指标，告诉我停下走选项 2/3，否则我按选项 1 继续 M2 板测。

## 2026-11-03 22:50 · M4（ELF 热修复）本次比赛范围放弃，转入后续工作
- 现象：时间线取舍（closed-loop-plan §六：先砍 M4 的 HTTP 下载与
  SHA-256，再砍场景 C 热修复）。11-04 18:00 功能冻结前完不成
  "ELF 加载 + 符号表 + L3 复核"全链路的验证。
- 已尝试 / 已排除的假设：空间评估已做（architecture-notes：修复版 ELF
  全流程 ≤15KB 峰值，对照最差 maxfree 18.7KB 仍有余量）——**放弃是
  工期原因，不是空间原因**。
- 影响：恢复阶梯只有 L1/L2，L2 失败或复现即升级给人（needs_human 锁存）；
  场景 C 只能做到"重启后复现 → 升级给人"（加分项，11-04 上午视时间）。
- 我建议的下一步：赛后按 SMARTFS 方案（上一条）落地持久化后补 M4。
- 需要 Ghee 做什么：知悉；如你仍想要 L3 现场演示，尽早说（工作量大）。

## 2026-11-04 10:38 · 已提交 AI 日志含个人邮箱，改写受限于红线 5
- 现象：提交版本文件的个人身份检查（11-04 指令第 5 点）发现
  logs/GerMa365/2026-11-01..03 三份 jsonl 含个人 Gmail（git config
  user.email 与提交 Author 行的工具输出）；另含上游提交元数据
  tianqin@xiaomi.com（Signed-off-by，公开上游信息，非我方泄露）。
  "GerMa365" 是 GitHub 登录名（logs/ 目录命名规范要求）；"Ghee" 是
  CLAUDE.md 模板自带称呼（模板要求 blockers 写"需要 Ghee 做什么"）。
  其余文件（docs/、README、patches/、tools/）：邮箱/手机号/身份证号
  零命中。
- 已尝试 / 已排除的假设：全库扫描已做（见上）；"已证实"类表述检查
  通过（README/patches/README/blockers 均为三层口径，无越界断言）。
- 冲突：红线 5 禁止改写 logs/ 下已有文件；但个人邮箱属敏感身份信息
  （红线 2 对密钥同理：保存前必须删掉）。且该邮箱已随 11-03 推送批次
  进入 fork 的 git 提交 Author 字段，历史改写需 force-push（红线 6 禁止）。
- 我建议的下一步（选项与风险）：
  A. 只管今后：git config user.email 换成
  GerMa365@users.noreply.github.com（此后新提交不再带个人邮箱；
  旧历史仍可见）；
  B. 例外脱敏：允许我改写三份 jsonl 里的邮箱字符串（违反红线 5
  的字面禁令，需你明确批准；历史 Author 仍在）；
  C. 维持现状：日志如实保留（AI 日志要求真实，且改动破坏可验证性）。
- 需要 Ghee 做什么：**已决定（2026-11-04 11:30）：选 C 维持现状**——
  logs/ 与 git config 均不动，个人邮箱随 git 元数据保留。

## 2026-11-04 19:12 · AI 日志 11-03 文件损坏原因：昨日捕获中断 + 水位线未推进的重复追加
- 现象：validate-log.py 对 logs/GerMa365/2026-11-03/claude-code__6945ef74….jsonl
  报 240 个错误：第 121 行 JSON 断裂（写入中断的半行），第 122–240 行是
  seq 1834–1952 的重复块（119 行），manifest 计数与实际行数不符。
- 已尝试 / 已排除的假设：
  - 时间戳定位：staging 与 logs 两份的 mtime 都是 **2026-11-03 19:40:47**
    （与 manifest.last_event_at 吻合），损坏发生在**昨天傍晚**，早于今天
    下午的 VS Code 卡死；**已排除"今天卡死损坏了 11-03 文件"**（该文件今天
    没有被写过）。今天卡死的足迹是另一处：staging 水位线 raw_event_count=6861，
    而 ~/.claude/projects/ 原始转录有 7035 行——**末尾 174 条事件从未被捕获**。
  - 逐行 seq 映射还原机制：行 1 = seq 1833（更早一次成功捕获）；行 2–120 =
    seq 1834–1952（19:40 捕获写到行 121 时**中断**，行断在一半）；行 122–1874
    = seq 1834–3586（随后的重试捕获按**未推进的水位线**重放同一原始切片，
    1834–1952 被重写一遍后续写到 3586，成功更新 manifest）。
  - 已排除原始转录损坏：7035 行 JSON 全部可解析，无断行。
  - 根因（收集器工具侧）：snapshot_core 的 append_events（追加事件）与
    write_manifest（推进水位线）非原子；捕获进程被杀即产生断行，下一次捕获
    又按旧水位线重放同一片事件——**追加不是幂等的**。
- 我建议的下一步（选项与风险）：
  1. 按计划从原始转录重新导出 11-01/11-02/11-03 三个日期文件并替换
     （Ghee 已指示）；风险：官方工具自带脱敏，与"原样"目标冲突（见下一条）。
  2. 赛后向收集器维护方提两个健壮性改进：写临时文件后原子改名；水位线按
     最后一条完整行回推。风险：无（不影响本次交付）。
- 需要 Ghee 做什么：知悉损坏发生时间与机制（昨天 19:40，非今天卡死）。

## 2026-11-04 19:15 · 重导"原样"目标与官方工具内置脱敏冲突（等待 Ghee 决定）
- 现象：团队决定旧 Key 随日志公开、事后作废。原始转录里旧 Key 出现在
  5 处 `Bearer <token>` 形态；官方转换器 snapshot_core 的 DEFAULT_REDACT_RULES
  **固定**替换 Bearer 令牌为 "Bearer ***REDACTED***"（另有 sk-/ghp_ 规则，
  本会话 0 命中），且**没有关闭开关**（redact.json 只能追加规则）。
- 已排除：手动改日志内容（Ghee 明令禁止）；换来源（staging 的 11-01 已被
  人工替换为 [REDACTED_API_KEY]，不可用）。
- 我建议的下一步（选项与风险）：
  A. 接受官方工具产物：5 处为 "Bearer ***REDACTED***"，其余全部原始，
     validate 可全绿。风险：旧 Key 不会真的出现在日志里（与"可以公开"
     的意图不符，但无安全问题）。
  B. 要求产物必须含原始 Key：官方工具做不到，需要你授权对产物做人工
     还原（等于人工修改日志内容，与你此前的规则冲突，需你明确改规则）。
- 需要 Ghee 做什么：选 A 或 B。默认按 A 推进（/tmp/log-reexport/ 试导出），
  logs/ 的替换仍等 20:15 后 + 你的确认。

## 2026-11-04 19:33 · 更正：上述"重导与内置脱敏冲突"不存在，重导可完全做到"原样"
- 现象：进一步核对发现，11-01 文件里 5 处 [REDACTED_API_KEY]（seq 98/107/115/121/399）
  对应的原始 Key **不是** Bearer/sk-/ghp_ 形态（官方脱敏规则逐条比对命中数为 0），
  官方引擎会原样带过；而 5 处 `Bearer <token>`（seq 3091/3092/3243，11-03 范围）
  当时就被官方工具脱敏为 "Bearer ***REDACTED***"（事件里有工具写的 redacted_count
  字段为证），重导结果与当时捕获输出一致，不构成对"原样"的修改。
- 已尝试：用官方 snapshot_core（不改一行）对原始转录重新导出三个日期文件到
  /tmp/log-reexport/，validate-log.py 结果 **ALL OK**（3 文件 3690 事件 0 错 0 警告）；
  11-03 无 JSON 错误与重复块，11-01 无 [REDACTED_API_KEY]（原始 Key 回归）。
- 与当前 logs/ 的差异（只统计）：5 处 Key 原样恢复；339 处仅时间戳不同（原始转录里
  无 timestamp 字段的元数据事件，官方代码用捕获时钟补时间戳，重导时补的是导出时钟，
  逐字节复现已不可能）；11-03 新增 103 条尾部事件（原 174 行从未被捕获）；
  11-03 删去 1 条断行 + 119 行重复块。
- 我建议的下一步：20:15 测试冻结后按计划用重导结果替换 logs/ 对应文件与 manifest
  （含把 e40f54d4 的 09-19 文件、557563b5 的 11-03 文件也登记进 manifest，
  消掉 4 条 orphan 警告，做到"全部通过"），随后本地提交，等 Ghee 确认再推送。
- 需要 Ghee 做什么：无需决策；如不同意"11-03 含 103 条尾部事件"或"补登记两个
  孤儿文件"，在替换前说一声即可（重导脚本可一键重生成）。

## 2026-11-05 00:23 · 推送完成，PR 创建被 fine-grained token 权限拒绝
- 现象：`feature/closed-loop` 已推送到 fork（`d363965..cf7bfb1`，15 个提交，
  含演示视频 docs/视频.7z）；调 GitHub REST API 在
  `open-vela/contest2026_330_neiheyoumuzhe` 建 PR 返回 403
  `Resource not accessible by personal access token`——本地 ~/.git-credentials
  里的 fine-grained PAT 对 base 仓库没有 Pull requests 写权限。
- 已尝试 / 已排除的假设：gh CLI 未安装；GitHub MCP 未配置；同一凭据
  `git push fork` 成功（对 fork 有写权限）；base 分支 `dev-ai-contest-2026`
  存在；`head=GerMa365:feature/closed-loop` 已在 fork 上（15 个提交）。
- 我建议的下一步（列出选项与各自风险）：
  1. Ghee 点 compare 链接一键建 PR（最省事、不动凭据）：
     https://github.com/open-vela/contest2026_330_neiheyoumuzhe/compare/dev-ai-contest-2026...GerMa365:feature/closed-loop
     （标题/正文我已备好，见会话汇报；带预填参数的长链接也一并给出）。
  2. 给现有 PAT 增加对 base 仓库的 Pull requests: write（或换 classic `repo` PAT）
     后我重试 API（风险：凭据权限扩大，需自行权衡；用完可收回）。
  3. Ghee 在 GitHub 网页手动建 PR，标题/正文粘贴我给的文本。
- 需要 Ghee 做什么：三选一即可；选项 1 两步（点链接 → Create pull request）。

## 2026-11-07 20:10 · esp-hal-3rdparty 工作副本丢失，重新 clone 后需手工重放 0005/0013
- 现象：M4 首次构建时发现
  `nuttx/arch/risc-v/src/esp32p4/esp-hal-3rdparty/`（build 系统经
  `arch/risc-v/src/chip -> esp32p4` 符号链接引用的 HAL 工作副本）不存在。
  11-05 22:34 的答辩版构建还在用它，删除发生在 11-05 22:34 之后、
  本次 19:46 构建之前；bash 历史与构建规则里均找不到删除动作，根因未定论。
  本次构建的自动 clone 又因网络中断（HTTP/2 CANCEL）失败了一次。
- 已尝试 / 已排除的假设：
  - 已排除"本次构建误删"：make 只在目标缺失时才走 clone，删除在先。
  - 已排除"bash 历史中的 rm"：无涉及该路径的删除命令。
  - /home/w/Project/knowngood_esp32p4/ 有一份 2026-08-13 的旧副本，但早于
    全部 SiliconLoop 补丁（MEMPROT 原样），不可直接使用。
- 影响与恢复路径（无板子风险，纯构建侧）：
  1. 重新 clone（Make.defs 自动 apply 0002 + mbedtls 补丁）；
  2. 手工重放 `0005-esp-hal-eth-link-timer-wdog.patch`（EMAC 需要）与
     `0013-esp32p4-pmp-allow-execute-from-heap.patch`（ELF 加载需要）——
     这两个不在任何自动挂钩里，原工作副本上是手工打的；
  3. 核对 `cpu_region_protect.c` RWX 与 `esp_eth.c` wdog 在位后重建。
- 后续建议（赛后）：把 0005/0013 一并纳入 `esp32p4/Make.defs` 的
  `.siliconloop_ready` 自动补丁块，消除"重 clone 后漏打手工补丁"的坑。
- 需要 Ghee 做什么：知悉；答辩版固件文件（~/siliconloop-defense-1105.bin）
  不受任何影响（它是独立 .bin，与 HAL 工作副本无关）。

## 2026-11-08 01:14 · HAL 工作副本再次丢失，根因已定位：configure.sh -e 触发 distclean 删除 HAL
- 现象：11-07 深夜重建 HAL（c6 副本拷贝 + checkout 8d0a8989 + mbedtls 0001/0002
  + HAL 0002/0005/0013 全部就位、.siliconloop_ready 已建）之后，带 PATH 重建
  固件时构建日志第 13 行出现 "Cloning Espressif HAL"，正在准备的 HAL 目录再次
  被清空重新 clone（且本次 clone 因网络 HTTP/2 中断失败）。同时查明了
  11-07 20:10 那次"删除根因未定论"的真相。
- 根因（代码级确认，非猜测）：
  1. `nuttx/tools/configure.sh -e <config>` 在 .config 与备份 defconfig 有差异
     时先跑 `make distclean`（configure.sh:114 distclean=y → :221）。
  2. `arch/risc-v/src/common/espressif/Make.defs:222` 的 `distclean::` 规则
     无条件 `rm -rf chip/esp-hal-3rdparty`——包括我们手工准备的工作副本。
  3. build.sh 每次跑 savedefconfig，把 defconfig 变更写回 nuttx/defconfig；
     我在 defconfig 加了 HELLO_APP_FIXED=y → 下一次 configure.sh -e 判定
     "有配置变化" → distclean → HAL 被删。
  4. 11-07 20:10 的"删除"也是同一机制（那次也是改了 defconfig 后构建），
     不是人为误删。
- 影响：HAL 重clone 后需重打 mbedtls 0001/0002 + HAL 0002/0005/0013；
  mbedtls 582ff48 需网络获取（apps_crypto_mbedtls.git 的 79M pack 里没有
  该 commit；c6 副本的子模块目录是空的）。HAL 已从 c6 副本重新拷贝并
  checkout 8d0a8989，0002/0005/0013 已重新打上；mbedtls 在网络重试中。
- 我建议的下一步（防再发，赛后处理，今晚不动 Make.defs）：
  1. 把 0005/0013 与"从本地副本恢复而非网络 clone"一并写进
     esp32p4/Make.defs 的 .siliconloop_ready 块（新增补丁，不动上游规则）。
  2. defconfig 冻结后不再改动（M4 的 HELLO_APP_FIXED=y 已进 .config 与
     nuttx/defconfig，后续构建 cmp 相等 → 不再触发 distclean）。
  3. 构建前 `ls chip/esp-hal-3rdparty/.siliconloop_ready` 作为例行检查。
- 需要 Ghee 做什么：知悉根因（非误删、非网络单因）；若认可建议 1，赛后
  按"新增补丁"流程落地。今晚 M4 板测不受阻（HAL 已恢复，mbedtls 拉取中）。

## 2026-11-09 08:10 · build.sh 符号链接解析回主工作区，主区被误重链（已归档，主区无损）
- 现象：为重建 M3 固件搭建了独立工作区 `/home/w/Project/openvela-m3rebuild/`，
  其中 build.sh 用符号链接指向主区。构建时 `build.sh` 内部
  `ROOTDIR=$(dirname $(readlink -f ${0}))` 把链接解析回主区实际路径，
  `ROOTDIR=$(realpath .../../..)` 得到主区根——两次"重建"实际都在
  主工作区执行（构建日志 `make: 进入目录 /home/w/Project/openvela/nuttx`）。
  第二次构建（11-09 00:13）在主区触发重新链接。
- 主区损害评估（逐项核实）：
  - 源码/defconfig：零变化（git diff 为空）；.config 完好（HELLO_APP_FIXED=y
    在，另有 .config.orig 备份）；
  - HAL 工作副本：完好（.siliconloop_ready 在位，未触发 distclean——
    .config 与 defconfig cmp 相等）；
  - 产物：nuttx.bin / System.map / nuttx.elf / nuttx.map / nuttx.hex 被
    重链（00:13），已全部改名归档为
    `nuttx/<名>.误重链-2026-11-09-0013-来源不明`（bin sha256
    f6e289cf…dc09a5，919,564 B），未删除；nuttx.manifest（47 B）删除
    （构建再生）。
  - 板子不受影响（未烧录任何东西，板上仍是答辩版固件）。
- 已查明（根因链，含证据）：
  1. 烧录 #3 固件（920,616 B，sha 99177f68…，11-08 08:14 产出）与当前
     提交源码一致：nsh_commands.o = 08:13:58（最后一次源码 Edit 08:13:34
     之后编译，size 显示 bss=0 即 16KB rb.0 不在）、tool_recover.o = 06:12
     （宏统一版）；板上 free heap 136,664 = 旧版 120,280 + 16,384 精确
     吻合。**此前"烧录 #3 是 0023/0024 过渡混合态、还带 16KB 缓冲"的
     判断是错误的**，依据的是 m4-build-5/6.log（01:24/01:29，0023 版，
     sram_seg=156,352）——那些构建早于源码修复，与烧录 #3 无关。
  2. 08:14 构建为何可信：会话日志（seq 1680–1695 时间段）显示 08:12–08:13
     三次 Edit 后 08:13:53 make 重编 nsh_commands.c（"CC: src/channels/
     nsh_commands.c" 在 08:14:08 输出中），08:14:21 用 `nm -S | grep -c
     'rb\.0'` = 0 验证过。
  3. 归档的 00:13 重链产物与烧录 #3 功能同源但哈希/布局不等：大小差
     1,052 B、drom 差 8 B、符号小漂移（tool_recover_execute −0x1FE、
     s_tls_raw_buf +0x18）。08:14 版 System.map 未留档，组装级差异
     （镜像头/对齐/归档序）无法逐步归因。
- 防再发（已提出修改建议，等 Ghee 确认后改 CLAUDE.md 第 6 节）：
  1. build.sh 只能用实体副本（cp），禁止符号链接到其他工作区；
  2. 每次固件构建后立即核对 System.map：预期符号的出现/消失
     （本次应无 rb.0）、sram_seg 大小与预期一致，并把 bin 的
     sha256 与 System.map 一并留档；
  3. 烧录前的固件必须是从当次构建日志能对应到"哪个 sha256、哪些
     .o 重编过"的产物。
- 影响：M3 重建推后（改用实体副本方案时再执行，见 Ghee 11-09 指示）；
  11-08 板测数据有效（烧录 #3 与提交源码一致），无需重测已完成的轮次；
  M4 内存回归结论的表述已按"待可复现固件重测"加注（m4-smoke-notes.md、
  patches/README 0024 节）。
- 需要 Ghee 做什么：知悉；确认 CLAUDE.md 第 6 节修改建议后我再动手。
