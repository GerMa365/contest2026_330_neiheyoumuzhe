# M2 执行面（m2-wip 分支工作稿）

> 状态：**WIP，不烧板、不测试**。M1 验收通过并打 `m1-done` 标签后合并、
> 应补丁、构建烧录、跑场景 B/C 验收（见文末集成清单）。
> 授权来源：Ghee 2026-11-03（50 轮回归期间可并行编写 M2，隔离到 m2-wip）。

## 内容

| 文件 | 说明 |
| --- | --- |
| `patches/0016-ai-agent-recover-task.patch` | recover_task 工具全量：tool_recover.c/h（新增）、tool_registry.c/h（注册 + TOOL_SEC_SENSITIVE）、Kconfig（SILOOP_RECOVERY_MODE） |
| `app/hello_app/buggy_app_main.c` | buggy_app 改造：SIGUSR1 软恢复、PID/mode 文件、"bug" 代码缺陷模式 |

## recover_task 设计（对齐 closed-loop-plan §3.1/3.2）

**"LLM 提议，确定性代码裁决"**：LLM 只给 `action`（resume/restart/hotfix，
即起始级）和 `target`；守卫、阶梯、复核全在 C 代码。

守卫顺序（全在 execute() 内）：
1. needs_human 标志存在 → 一律拒绝（L3 失败后人工接管，复位前不自动处置）
2. 目标白名单：仅 `buggy_app` / `buggy_app_fixed`（nsh、ai_agent、网络线程永不可动）
3. Kconfig 模式：0=off / 1=dry-run / 2=confirm（需 confirm:true）/ 3=auto
4. 冷却 120s（一个心跳周期内同目标不重复处置）+ 每小时上限 6 次
5. 独立重新采样：两次读心跳差 Δ=0 才允许动手（Δ>0 说明任务已健康，拒动）

恢复阶梯（从 LLM 指定的级起步，失败升一级）：
- **L1 resume**：读 PID 文件 → SIGUSR1 → buggy_app 重开消费者 → 复核
- **L2 restart**：SIGTERM → 按 mode 文件**原样重启**（代码缺陷必须复现，
  阶梯才能走 L1→L2→L3；stall 类故障靠 L1 恢复）→ 复核
- **L3 hotfix**：SIGTERM → 启动修复版 ELF（/data/patches/buggy_app_fixed，
  M4 交付物）→ 复核；仍失败 → needs_human

复核：处置后采样 Δ>0 = recovered；JSON 一行 ≤256B；
actions.log 只追加（时间,目标,动作,pre,post,结果）。

## buggy_app 改造要点

- `signal(SIGUSR1, on_usr1)`：消费者重开（异步信号安全，仅置标志）
- PID 文件 + mode 文件（stall/bug/normal）：让 recover_task 精确定位、
  并按原工作负载重启
- "bug" 模式：fifo_put 计数漂移（g_count += 2），FIFO 永久填满、生产者
  死等——SIGUSR1 无效、重启复现、只有修复版 ELF 能愈（正好走满阶梯）

## m1-done 后集成清单（合并到 feature/closed-loop 之后做）

1. `git merge m2-wip`；`patch -p1` 应用 0016 到 packages/ai_agent 工作区
   （干净副本先 `git apply --check`），touch 相关源文件重编
2. buggy_app 部署 ELFs：`apps/bin/buggy_app` → 板上 `/data/ai_agent/bin/`
   （L2 重启用）；修复版 → `/data/patches/buggy_app_fixed`（M4 构建）
   ——注意 /data 是 tmpfs，重启即丢，长期方案见 blockers.md（SMARTFS）
3. Kconfig 模式确认（demo 用 auto=3）；编译验证 recover_task 注册成功
4. 场景 B 验收：stall 注入 → L1 SIGUSR1 恢复 → 误处置 0
   （A、B 各 20 轮，B 恢复成功率 ≥90%）
5. 场景 C 预演（M4 后完整）：bug 注入 → L1 无效 → L2 复现 → L3 愈
6. 验证 recover_task 重启路径无 TLS 泄漏类问题（architecture-notes
   附加发现 2 的教训）

## 未决/注意

- posix_spawn 需要 binfmt ELF 支持（0014 已修 elf icache，应可用）；
  集成时若 spawn API 不可用，退回 task_spawn/重编内建入口
- L2/L3 各阻塞 agent loop ~10s（等待+复核采样），demo 可接受；
  若并行诊断受影响，改为异步处置+轮询复核（M3 再议）
- 确认模式（mode=2）的 confirm 字段已进 schema；人机确认 UI 不在 M2 范围
