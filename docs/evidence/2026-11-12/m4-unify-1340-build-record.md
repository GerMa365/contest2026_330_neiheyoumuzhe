# 13.4.0 统一工具链重编（1025 全量扫描 + 清单删除 + 重链）

日期：2026-11-12 00:24–00:29（CST）
背景：11-10 编译失败根因为编译器混用（build.sh 走 prebuilts GCC 13.4.0，
裸 make 走 ~/.bashrc 的 GCC 14.2.0；GCC 14 将 nxsched_usleep 隐式声明
从 warning 升为 error）。Ghee 决定统一 prebuilts 13.4.0（见
docs/blockers.md 2026-11-11 12:00 条目）。

## 扫描与清单

- 全工作区 `/home/w/Project/openvela` 共 3,254 个 .o 的 DWARF producer
  全量扫描（结果 /tmp/claude-check/scan-v2-result.txt，11-11 21:55）。
- 14.2.0 残留仅 3 个，全在专属仓 app/ 目录（上会话扫描漏了该目录）：
  1. app/hello_app/buggy_app_main.c.…hello_app.o（删除前 sha256
     90daa8c8eacb755f0b3d3dcfa81c50e2a414853e3e5998e152c9d1c8edeb1239）
  2. app/hello_app/buggy_app_main.c.…hello_app_1.o（同源重复产物，同 sha256）
  3. app/hello_app_fixed/buggy_app_fixed_main.c.…hello_app_fixed.o（sha256
     52ea859a9ee6d9e9387e3df6df5926a7b2c36686e10f90ac85c46d3e0839de38）
- Ghee 确认后删除上述 3 个（删除前 sha256 已记录）。
- 第二类 6 个汇编 .o（无 DWARF producer 属预期，14.2.0 窗口后由
  13.4.0 重编生成）按 Ghee 指示保留，未删除；时间戳：
  - nuttx/arch/risc-v/src/fork.o                2026-11-11 21:19:24.623 +0800
  - nuttx/arch/risc-v/src/esp_vectors.o         2026-11-11 21:19:24.407 +0800
  - nuttx/arch/risc-v/src/riscv_mhartid.o       2026-11-11 21:19:24.487 +0800
  - nuttx/arch/risc-v/src/riscv_exception_common.o 2026-11-11 21:19:24.423 +0800
  - nuttx/arch/risc-v/src/esp_head.o            2026-11-11 21:20:56.480 +0800
  - nuttx/arch/risc-v/src/riscv_saveusercontext.o 2026-11-11 21:19:24.556 +0800
- 另有 960 个 11-09 之前 mtime 的无编译器信息对象（prebuilts 发行版
  crt0/crtbegin 等 + 11-08 01:16 elf_globals.o + 11-08 01:23 HAL
  sleep_cpu_asm.o），不进 nuttx ELF 判定范围，未处理。

## 本次构建

- 编译器：PATH 前置
  `PATH=/home/w/Project/openvela/prebuilts/gcc/linux-x86_64/riscv-none-elf/bin:$PATH`
  编译前确认 `riscv-none-elf-gcc (GCC) 13.4.0`（记录见
  /tmp/claude-check/build-1340-record.txt 的复制件）。
- 命令：`cd /home/w/Project/openvela/nuttx && PATH=$PB:$HOME/esp-venv/bin:$PATH make -j8`
  （未运行 build.sh；.config 带 CONFIG_SILOOP_MEMPROBE=y，与
  .config.orig 差异仅 BASE_DEFCONFIG + 该行，无漂移）。
- 重编对象（make 日志 CC/LD 行）：buggy_app_main.c、
  buggy_app_fixed_main.c（13.4.0）、misc/lib_utsname.c（mtime 触发）、
  libapps.a/libc.a staging → LD nuttx → MKIMAGE nuttx.bin。
  完整日志：m4-unify-1340-make.log。
- 产物（00:29）：
  - nuttx      16,585,172 B  sha256 8b6195290da0448151e29835f9b13faf0c8b0df99ce8ca079a185ec4eee01bf1
  - nuttx.bin   919,652 B    sha256 6a2daa40ee6aa4f244050076d1d19f5821eb7dc3a6482ef9b1753946aeacd669
  - System.map 随附（本目录 m4-unify-1340-System.map，sha256
    054739dbc191d34ff7844ce8e3b3b02680c703a08e1a8cc8ae2fc245cd4dfc7f）。
    完整链接器映像 nuttx.map（21 MB）不入库，留在 nuttx/nuttx.map。

## 判据核对

- 最终判据 **通过**：nuttx ELF .debug_str 中 GNU C producer 只出现
  `GNU C17 13.4.0`，14.2.0 编译单元计数 = 0。
- 新编 3 个 app .o 的 producer 均为 `GNU C17 13.4.0`（抽验）。
- System.map：`rb.0` 符号 0 处（符合 0024 预期）；`sloop_memprobe_peak`
  无独立符号——static 单调用点被 -Os 内联进 tls_write_request，属预期；
  打点格式串 `[sloop-memprobe] peak pre-write req=%zu maxfree=%u free=%u`
  已确认在 nuttx ELF 内，vela_tls.o 引用 `U mallinfo`，0025 打点已编入。
- 链接区段：sram_seg 139,968 B = 156,352（0023 时代）− 16,384（0024
  删除的 16KB 静态缓冲），精确吻合；drom_seg 877,488 B。

## 状态

- 未烧录（等 Ghee 指示）。
- 注意：11-10 08:14 的 nuttx.bin（920,444 B，含 0025 源码但打点为空）
  与 11-11 21:21 的 nuttx.bin（919,644 B，14.2.0 混编）均作废，
  以本次 00:29 产物为准。
