# B1 干净重建失败摘录（2026-11-25）

环境：/tmp/rb-b1，上游基线（nuttx dd92bcf42573 / apps dcc6a95c3b32 /
ai_agent 31faed70f683 / HAL 8d0a89891008 / mbedtls 582ff482038d）+
已有补丁（0001–0005、0007–0024、0029–0032，**不含** 0025–0028、0033）。
工具链：prebuilts GCC 13.4.0（构建命令行已核对版本）。配置：
vendor siliconloop defconfig → process_config.sh → olddefconfig（.config
3189 行）。构建命令：裸 make -j8（Ghee 已批准，见 cc-plan-techdebt.md §5.2）。

预期：0032 在 agent_loop.c:1808 调用 vela_tls_pool_release_idle()，
其实现在未导出的 0027 中 → 链接失败。

实际结果：构建失败（rc=2），但**早于链接，在编译阶段就失败**，两处：

1. `src/tools/tool_registry.h:35:28: error: expected identifier before
   numeric constant`（宏 TOOL_SEC_SENSITIVE 0x01u 撞 tool_guard.h 枚举
   成员，note 指向 tool_guard.h:30 的展开点）
   ——rb-b1 的 include 链（agent_mem.h → tool_registry.h → tool_guard.h）
   让 0017 的宏先于枚举定义。工作区此前能编译过，是因为工作区已打 0033
   （删宏）；A5 的推断（宏与枚举同名单独见即硬错误、能否编译取决于
   include 顺序）在本重建中得到直接证实。
2. `src/core/agent_loop.c:1808:9: warning: implicit declaration of
   function 'vela_tls_pool_release_idle'`——预期的"实现未导出"信号
   （因 0027 缺失）；本应发展为链接期 undefined reference，但编译在
   错误 1 处中止，未到达链接。

结论：现有补丁集确实不完整、无法独立重建——且比预期更早失败（编译期
而非链接期）。0025–0028 + 0033 补齐后应能通过（B2）。

完整日志：b1-full-build.log（同目录，115,848 字节）。
