# M4 构建产物与符号审计（2026-11-08，板测前）

## 验收标准（对应验收表第 1 项的前半段）

1. M4 固件与修复版 payload 在宿主机构建成功（板上烧录与 fwpush 实测
   待 Ghee 确认窗口后进行）。
2. 修复版 ELF 的未定义符号（`nm -u`）逐项核对，导出表精确匹配；
   结果经 Ghee 确认后烧板（验收表明确要求"结果先给你看、你点头后"）。

## 构建

- 固件：`nuttx/nuttx.bin` 919,624 B
  sha256 `5e92f1a85570cdf8c129de9f4c6def729c887d99f3b8318c2fbb3e158920ac7b`
  （答辩版 906,600 B +13KB：L3 链路 + fwpush + 符号表；HELLO_APP 与
  HELLO_APP_FIXED 同时启用）
- payload：`apps/bin/buggy_app_fixed`，6,388 B，ELF32 LSB relocatable
  RISC-V RVC soft-float，MODULE=m 构建流（与 9 月 buggy_app 同路径）
- host 测试（ASan/UBSan）：recover_guard_test / fallback_report_test /
  asround_test 全绿（SILILOOP_HOST_TEST 剥离 exec_spawn 路径）

## 符号审计（nm -u apps/bin/buggy_app_fixed，共 16 项）

```
         U fclose
         U fopen
         U fprintf
         U fputs
         U getpid
         U printf
         U pthread_create
         U pthread_mutex_lock
         U pthread_mutex_unlock
         U puts
         U sched_getparam
         U sched_setparam
         U signal
         U sleep
         U strcmp
         U usleep
```

hotfix_exports.c（0022）导出表 = 上表 16 项，逐项精确匹配、不多导出。
其中 `signal` 是 elf 示例生成表（34 符号）没有、而修复版必需的符号
（M4 计划第 0.3 点预判命中）。

## 重定位类型核对

.rela.text 218 项，类型集合：
R_RISCV_HI20×26 / LO12_I×36 / LO12_S×6 / CALL_PLT×31 / RELAX×99 /
BRANCH×7 / RVC_BRANCH×8 / RVC_JUMP×5——与 9 月板上加载成功的 elf 示例
产物（hello 等）同一集合，无数据段重定位（.data 无 .rela）。

## 补丁链验证

干净基线（git archive HEAD）依次应用
0007→0008→0009→0010→0011→0012→0015→0016→0017→0018→0019→0020→0021→
0022→0023 全部通过，产物与工作树逐文件 diff 一致。

## 同日环境事件

HAL 工作副本两度丢失的根因已定位并写入 blockers.md（2026-11-08 01:14
条）：configure.sh -e 触发 distclean 删除 chip/esp-hal-3rdparty。
当日已从 c6 副本恢复（checkout 8d0a8989 + HAL 0002/0005/0013 +
mbedtls 582ff48 + 0001/0002），核对清单全过。本文件上列固件即恢复后
构建产物。

## 板测计划（待 Ghee 确认后执行，按验收表 2026-11-07 18:05 版）

smoke → C 正常路径首轮 → A×10 → C 剩余 4 轮 → 失败路径（缺包/坏包）
→ L3 后持续运行 → B×3；时间不够先砍持续运行与 B 轮数，A 和 C 不砍。
