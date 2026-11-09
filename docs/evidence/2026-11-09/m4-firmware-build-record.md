# M4 固件构建留档（2026-11-09，与提交 55d4128/4b28b11 对应）

## 构建方式
- 主工作区规范增量编译：`make -j8`（PATH 含 esp-venv，无 configure、
  无 distclean；构建日志 /tmp/m4-final-build.log，RC=0）
- 构建前基线：.config sha256 ef446914…、HAL .siliconloop_ready 在位、
  nuttx/bin 缺失（00:13 误重链产物已归档），全新链接
- 重编清单：仅 libs/libc/misc/lib_utsname.c（时间戳宏）+ 全新 LD

## 核对结果（按 CLAUDE.md 第 6 节新规则）
| 项 | 预期 | 实测 | 结果 |
|---|---|---|---|
| rb.0（16KB 静态回读缓冲） | 不在 System.map | `nm nuttx \| grep -c ' rb\.0$'` = 0 | ✅ |
| sram_seg | 与流式版一致（139,968） | 139,968 B | ✅ |
| bin 大小 | 与烧录 #3 一致（920,616） | 920,616 B | ✅ |
| g_hotfix_exports | 400d230c | 400d230c | ✅ |
| tool_recover_execute | 4004ed0a | 4004ed0a | ✅ |
| s_req_buf / s_jobs / s_tls_raw_buf | 4ff59a90 / 4ff54908 / 4ff575e0 | 同 | ✅ |

（右侧预期值来自 11-08 08:14 版烧录 #3 固件的符号快照，5/5 一致；
本次构建即烧录 #3 的可复现重出。）

## 产物
- nuttx.bin：920,616 B，sha256 见下方烧录请求
- System.map：本目录 m4-final-System.map
- 段大小：irom 601,126 / sram 139,968 / drom 877,416 B
- 版本串：dd92bcf4257-dirty Nov  9 2026 08:36:20

## 与 11-08 归档产物（误重链版）的差异说明
误重链版（f6e289cf…，919,564 B）的 .flash.text 比本次小 1,050 B，
libgcc 浮点例程（__divdf3 起）地址系统性偏移——归因于该次构建在
m3rebuild 工作区语境下的链接环境差异；本记录的固件以主工作区
规范构建为准。
