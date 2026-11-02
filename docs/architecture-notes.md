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
