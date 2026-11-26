# B2 干净重建验证（2026-11-25/26）

## 环境

- 树：/tmp/rb-b2 —— 四个 repo 管理目录 `git archive <基线> | tar -x`
  （nuttx dd92bcf42573 / apps dcc6a95c3b32 / ai_agent 31faed70f683 /
  vendor 按补丁基线），HAL 8d0a89891008 从 rb-b1 复制（cmp 证实 0013
  内容一致，无需二次 apply）；全部 32 个补丁（0001–0005、0007–0033，
  无 0006）按 README 顺序应用。
- 配置：siliconloop defconfig → process_config.sh → olddefconfig。
- 工具链：prebuilts GCC 13.4.0（每次 make 前命令行核对版本）。
- 构建：裸 make -j8（Ghee 已批准，cc-plan-techdebt.md §5.2）。

## 构建过程（4 轮，日志同目录）

1. `rb-b2-build.log`：编译全部通过（B1 的两处错误——tool_registry.h:35
   宏撞枚举、agent_loop.c:1808 implicit declaration——均消失，证明
   0025–0028 + 0033 补齐了补丁集缺口），**链接失败**：
   `tool_media.c:1216 undefined reference to cJSON_GetNumberValue`。
2. 根因诊断（见 b2-cjson-link-failure.md）：cJSON 源码不在 git
   （.gitignore 忽略 /cJSON*，Makefile 按需下载），工作区静默使用
   2026-08-16 遗留的 1.7.15 解包（含 GetNumberValue），干净树按
   CONFIG_NETUTILS_CJSON_VERSION="1.7.12" 下载的 1.7.12 无该函数。
   tool_media.c 的调用是 ai_agent 基线自带（无补丁触碰该文件）。
3. `rb-b2-build2.log`/`rb-b2-build3.log`：换入 1.7.15 源后链接通过；
   但读回的 cJSON .o 是工作区带过来的（14.2.0 编译产物，debug_str
   含 2 处 14.2.0）→ 不合规，重取官方 v1.7.15.tar.gz 原包解入。
4. `rb-b2-build4.log`：touch cJSON 源强制重编，**全链成功**：
   链接 + esptool elf2image（v5.3.1，/home/w/esp-venv）→ nuttx.bin。
   `rb-b2-mkimage2.log` 为中间一轮的 mkimage 留档。

## 验收判据结果

| 判据 | 结果 |
| --- | --- |
| 编译+链接+mkimage 成功 | ✅ nuttx（16,505,476 B）+ nuttx.bin（913,832 B） |
| 14.2.0 双判据 = 0 | ✅ readelf -p .debug_str = 0；-p .debug_line_str = 0（含 cJSON 4 个 .o 逐一 = 0） |
| System.map 含 vela_tls_pool_release_idle | ✅ 400478f6 T |
| System.map 含 sloop_memprobe_peak | ⚠️ 无独立符号——0025 的探针是 static 函数且被 GCC 13.4.0 内联进 tls_write_request（反汇编实证：40047174 `jal mallinfo`，ELF 内含 `[sloop-memprobe]` 字符串）。判据原文写法不成立，改为"内联调用 + 字符串存在"，两项均验证通过 |
| .config 行级 diff 逐行解释 | ✅ 见下 |

## .config 行级 diff（rb-b2 vs 工作区快照，总 80 diff 行）

- **注释/菜单框架行 69**（`#`, `# Xiaomi Projects`, `# end of …` 等）：
  olddefconfig 对菜单结构输出的排版差异，无语义。
- **"not set" 行 10**（WIFI_TEST/SHOW_LOGO/PYXIS_SYSMON/LUNCHER_MINI_APP/
  LED_RGB_TEST/EXAMPLES_* 等）：工作区有而 rb-b2 无——工作区 .config
  停留在更早的 defconfig 世代，这几个符号后来从 defconfig/Kconfig
  消失；olddefconfig 不再输出已不存在的符号。无语义（都是 not set）。
- **实质差异 11 项，全部属于工作区 PSRAM 实验（批 3）状态，defconfig
  本身没有**：
  - `CONFIG_ESPRESSIF_SPIRAM=y` + BOOT_INIT/IGNORE_NOTFOUND/MEMTEST/
    SPEED/SPEED_200M（6 项）= PSRAM 第二堆实验（siliconloop_exp 批次，
    0031 重定向依赖它）；
  - `CONFIG_MBEDTLS_PLATFORM_MEMORY=y` = 0031 的 mbedTLS 重定向开关；
  - `CONFIG_FACTORY_TEST=y` + PRIORITY/TASK_STACKSIZE（3 项）=
    11-23 心跳 400 修复板测时顺手带入的演示项（vendor 菜单块，与
    闭环无关，待批 4 决定去留）。
- **相同的关键项**：SILOOP_MEMPROBE=y（0025）、BASE_DEFCONFIG="-dirty"
  （两边一致，历史遗留字符串）。

## 结论

补齐 0025–0028 + 0033 后，补丁集可在干净副本上独立重建出完整固件；
唯一阻碍是一处**环境漂移**（cJSON 解包目录版本 ≠ 配置声明版本），
不是补丁集缺口。工作区 .config 相对 defconfig 的额外状态 = PSRAM
实验 + FACTORY_TEST，与既有结论一致。

## 产物指纹

- nuttx: b7c1783ca0ed495191d12b1d2d997eb0a6933116ed0a023ba99fc14f754d927a（16,505,476 B，build4 终轮）
- nuttx.bin (913,832 B): f2361fe2a3d0b013fde2f5525a3660eac2720c4fd9e6aa91ef08c334aeacddce
- System.map: 3c35565ccca04d264b72a70455518cde964a6325ab00d7a956fe4bc413b88b7b

**未烧录**——本验证只证明补丁集可重建，产物不作为板测固件（板上
运行仍以工作区构建流程为准）。

## 遗留（待 Ghee 决定）

cJSON 版本钉死：建议 defconfig 加 `CONFIG_NETUTILS_CJSON_VERSION="1.7.15"`
（或补丁内改 Kconfig 默认值），使配置与 tool_media.c 依赖一致；
工作区的漂移解包也应同步。详见 b2-cjson-link-failure.md。
