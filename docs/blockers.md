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
