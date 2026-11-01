# SiliconLoop · Claude Code 工作手册

本文件位于参赛仓库根目录 `contest2026_330_neiheyoumuzhe/CLAUDE.md`，由 openvela 工作区根目录的 `CLAUDE.md` 导入，每次会话自动加载。
**需求来源**是 `docs/closed-loop-plan.md`（做什么、验收标准）；**本文件**是规则（怎么做、不能做什么）。两者冲突时以本文件为准，并在 `docs/blockers.md` 记录。

---

## 0. 本机环境（已由 Claude Code 代为核实并填写；改动前先在 blockers 里说明）

| 项目 | 值 |
| --- | --- |
| openvela 工作区根目录（下称 ROOT） | `/home/w/Project/openvela` |
| 串口设备 | `/dev/ttyACM0` |
| 操作系统 | Linux（Ubuntu，内核 6.8.0-138-generic） |
| 参赛仓库在工作区内的远程名 | `origin` → https://github.com/open-vela/contest2026_330_neiheyoumuzhe |
| fork 远程 | `fork` → `https://github.com/GerMa365/contest2026_330_neiheyoumuzhe.git` |
| esptool | `/home/w/esp-venv/bin/esptool` v5.3.1（虚拟环境 /home/w/esp-venv，操作板子的脚本一律用它） |
| 答辩人 | Ghee（嵌入式零基础，日报要让她能看懂并讲出来） |

下文所有相对路径都以 ROOT 为起点；`REPO` 指 `contest2026_330_neiheyoumuzhe/`。

---

## 1. 红线（任何情况下都不能做）

1. **烧录只能用 `REPO/tools/hil/flash.sh`**，地址固定 `0x2000`。禁止直接调用 `esptool write_flash / erase_flash / erase_region`。写 `0x0` 会覆盖 bootloader。
2. **不读取、不打印、不提交 `packages/ai_agent/include/agent_secrets.h`**。日志、证据、提交信息里出现 API Key 或 `Authorization` 头，必须先删掉再保存。AI Coding 日志会公开提交给评审。
3. **不执行 `repo sync`**：它会重置 nuttx、apps、packages 等目录，打过的补丁全部丢失。确需同步时写进 blockers 等 Ghee 决定。
4. 不改 `CONFIG_ESP_SYSTEM_MEMPROT`（已知会导致无法启动）。
5. 不删除、不改写已有的补丁 0001–0014、`docs/evidence/` 下已有日志、`logs/` 下已有文件。
6. 不 `git push --force`，不直接推送到参赛仓库远程，只推送到 `fork`。
7. 不给 Agent 开放 `reboot`、`kill` 等 shell 命令。所有处置动作只能经由 `recover_task` 工具执行。
8. 不让 Agent 在运行时生成或编译代码。热修复用的 ELF 由开发阶段预先构建。

---

## 2. 工作方式

- **只做当前指令指定的里程碑**。任务与验收标准见 `docs/closed-loop-plan.md` 第四节。完成后停下汇报，不自行开始下一个。
- **每次会话开始**：先读 `docs/daily/` 最新一份日报和 `docs/blockers.md`，再读当前里程碑涉及的代码。
- **先读后改**：改任何文件前先读懂相关代码。规划里的方案与代码事实冲突时，以代码为准，结论写入 `docs/architecture-notes.md`。
- **验收靠板上实测**：每条验收标准都要有对应的串口原始日志。不能用"理论上可行""应该能过"代替实测结果。
- **小步提交**：每满足一条验收标准就提交一次。
- **完成一个里程碑时**：确认全部验收项都有证据 → 提交 → 打标签 `mN-done` → 写日报 → 汇报并停止。

---

## 3. 闭环设计约束（实现时不可偏离）

### 3.1 数据流

```
心跳服务（每 120 s）→ Agent ReAct 循环（LLM + 诊断 Skill v2，只读采样心跳计数 / ps / free）
  → 判定 Δ = 0 ？
      否 → 报告 healthy，不处置
      是 → 调用 recover_task（C 代码）
             ① 守卫：目标白名单 → 冷却与频率 → 独立重新采样，确认 Δ = 0（否则拒绝执行）
             ② 恢复阶梯：L1 软恢复（SIGUSR1 唤醒消费者）→ L2 重启任务 → L3 ELF 热修复（加载 /data/patches/ 下修复版）
             ③ 复核：两次采样 Δ > 0 → 已恢复；Δ = 0 或恢复后复现 → 升一级；L3 仍失败 → 升级给人
  → 写 report.md（六段式）+ actions.log（审计）
```

### 3.2 必须遵守的设计规则

- **"LLM 提议，确定性代码裁决"**：LLM 只决定是否调用、从哪一级开始；执行、执行前确认、执行后复核全部在 `recover_task` 的 C 代码里完成。
- `recover_task` 注册为 `TOOL_SEC_SENSITIVE`，入参 `action`（`resume` / `restart` / `hotfix`）与 `target`。
- **目标白名单只有 `buggy_app`**（及热修复后的修复版进程）。nsh、ai_agent 自身、网络线程、idle 等系统任务永远不可作为目标。
- **冷却**：同一目标在一个心跳周期内不重复处置；每小时处置次数设上限（常量写在代码里并在补丁 README 说明）。
- L3 失败后，该目标标记为"需人工介入"，在复位前不再自动处置。
- **工具返回值只有一行 JSON，不超过 256 字节**，例如
  `{"level":2,"action":"restart","target":"buggy_app","pre_delta":0,"post_delta":37,"result":"recovered"}`。
  这是为了控制 LLM 请求体大小。
- `actions.log` 只追加，每次处置一行：时间、目标、动作、处置前后 Δ、结果。
- Kconfig 闭环模式开关：`off` / `dry-run`（只记录不执行）/ `confirm`（等人确认）/ `auto`。
- 现有诊断判据（心跳增量）不改变语义。

---

## 4. 资源约束

- 堆只有约 404 KB，**瓶颈是最大连续空闲块**，不是总空闲量。原 162 轮回归的 8 次失败都发生在第 7 步，原因是序列化约 12.5 KB 请求体时 OOM。
- 新代码避免单次分配超过 4 KB；优先用静态缓冲区。
- 每个里程碑都记录关键步骤前后的 `free` 输出（含最大空闲块），与 M0 基线对比。最大空闲块比基线明显变差时停下汇报。
- ELF 代码段必须放在内部 SRAM（补丁 0013 只放开了 PMP entry 6 与 9 的执行权限），不能放在 PSRAM。

---

## 5. 代码与补丁规范

- **repo 管理的上游目录**：`nuttx/`、`apps/`、`packages/ai_agent/`、`vendor/openvela/`、`nuttx/arch/risc-v/src/esp32p4/esp-hal-3rdparty/`。在这些目录里的改动**必须导出为补丁**，存到 `REPO/patches/`：
  - 编号从 `0015` 起连续递增（历史上没有 0006，不要补用）。
  - 命名：`00NN-<目标仓库>-<简述>.patch`，例如 `0015-ai-agent-recover-task-tool.patch`。
  - 已有补丁的文件需要再改时（如 0008 白名单），**新增一个增量补丁**，不改旧补丁。
  - 每个新补丁在 `patches/README.md` 补一节，格式与现有一致：性质、目标仓库、基线提交、解决的问题、根因、解法、局限、验证记录。
  - 在干净副本上用 `git apply --check` 验证可应用。repo 管理的仓库不能直接 `git clone`，用 `git archive <基线> | tar -x -C /tmp/<dir>` 导出（见 `patches/README.md`）。
  - README "运行方式"里的补丁应用顺序同步更新。
- **参赛仓库内的代码**（`REPO/app/`、`REPO/board/`、`REPO/tools/`）直接提交。新增应用目录要仿照 `app/hello_app/` 写 Kconfig、Make.defs、Makefile、CMakeLists.txt，并在 `contest2026_330_neiheyoumuzhe.xml` 加 `<linkfile>` 映射。
- **代码风格**跟随所在文件：ai_agent 为 4 空格缩进；nuttx 为 NuttX 风格。注释用英文，以 `SiliconLoop:` 开头说明"为什么"，参考补丁 0008。
- **构建配置**：在 `siliconloop` 配置上开发。M0 先打标签 `baseline-0920`，并把基线固件复制到仓库外 `~/siliconloop-backup/`，作为随时可回退的保底版本。PSRAM 等高风险实验先在新配置目录 `siliconloop_exp` 里做，验收通过后再合并回 `siliconloop`。

---

## 6. 构建、烧录、串口

```bash
cd ROOT
./build.sh vendor/openvela/boards/contest2026_330_board/configs/siliconloop -j8
PORT=<串口> contest2026_330_neiheyoumuzhe/tools/hil/flash.sh
```

- 串口交互用 Python（pyserial）脚本完成，**不要用 picocom 等交互式终端**，会话里无法操作 TUI。
- 板子复位或烧录后 USB 会重新枚举，等待串口设备重新出现（最多 15 秒）再连接。
- 硬复位通过串口 RTS/DTR 完成；仍无响应时写进 blockers，等 Ghee 手动复位。
- 完整演示需要 `agent_secrets.h`。只用 `ls` 确认它存在，不读取其内容。

---

## 7. 测试与证据

- 每个结论都要有原始串口日志：`REPO/docs/evidence/YYYY-MM-DD/<名称>.log`。汇总写成同目录下的 `.md`，并引用日志文件名。
- 保存日志前检查并删除密钥、Token、`Authorization` 头。
- 长时间回归用 `nohup` 在后台运行，输出写入文件，会话里定期查看进度，不要阻塞会话。
- 统计时把**网络 / LLM 服务失败**与**功能失败**分开计数。
- **场景 A（健康）出现任何一次误处置，立即停止并排查**，这是最重要的指标。

---

## 8. Git

- 工作分支：`feature/closed-loop`，从参赛仓库的 `dev-ai-contest-2026` 切出。
- 只推送到 `fork` 远程；PR 由 Ghee 在每个里程碑验收后发起并合入。
- 提交信息沿用现有风格：`feat(L4): …`、`fix(ai-agent): …`、`docs(evidence): …`、`test(hil): …`。
- 不提交编译产物和临时文件（参考 `.gitignore`）。

---

## 9. 必须停下来等 Ghee 的情况

1. 同一问题连续 3 次修复失败。
2. 需要人动手：插拔、按复位键、接网线。
3. 需要密钥、账号、额度、付费。
4. 需要改动本文件的红线、范围或规划中的设计约束。
5. 场景 A 出现误处置。
6. 最大空闲块明显低于基线。
7. 任何不确定是否会损坏板子或丢失数据的操作。

停下时在 `docs/blockers.md` 追加一条：

```markdown
## YYYY-MM-DD HH:MM · <一句话标题>
- 现象：
- 已尝试 / 已排除的假设：
- 我建议的下一步（列出选项与各自风险）：
- 需要 Ghee 做什么：
```

---

## 10. 日报格式（`docs/daily/YYYY-MM-DD.md`，中文）

读者是答辩人 Ghee。她需要能把每个改动向评委讲清楚。

```markdown
# YYYY-MM-DD 日报

## 今日完成
- 对应哪条验收标准 · 结果 · 证据日志路径

## 关键决策与理由
- 决策：…  理由：…  放弃的方案：…

## 新术语
- 术语：一句专业定义（按评委会用的说法）。补充类比：一句通俗比喻。

## 数据
- 关键指标与基线对比（最大空闲块、成功率等）

## 问题与风险

## 下一步

## 需要 Ghee 做的事
```
