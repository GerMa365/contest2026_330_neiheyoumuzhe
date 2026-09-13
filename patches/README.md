# nuttx 公共仓库补丁

## 这是什么

ESP32-P4 在 openvela `nuttx` 仓库中的支持代码。这些改动位于 repo 管理的
上游公共仓库，无法随队伍仓库提交，因此以补丁形式保存在此。

- 基线提交：`dd92bcf425738734d1b8aed09c2bd4dbe3f2e438`
- 补丁规模：31 个文件，9385 行新增，4 行删除
- HAL 依赖：`ESP_HAL_3RDPARTY_VERSION = 8d0a898910084206721a0892ab093021bca1496a`
  （记录在 `arch/risc-v/src/esp32p4/Make.defs`，构建系统自动拉取，
   584MB 的 HAL 源码**不包含**在本补丁内）

## 什么时候需要用

- 执行过 `repo sync`
- 换了开发机器
- `nuttx` 目录被重置

## 怎么用

```bash
cd <openvela 根目录>/nuttx
git apply --check ../contest2026_330_neiheyoumuzhe/patches/0001-esp32p4-support-for-openvela.patch
git apply ../contest2026_330_neiheyoumuzhe/patches/0001-esp32p4-support-for-openvela.patch
```

`--check` 只检查不修改，先跑它确认无冲突。

## 补丁内容

| 文件 | 改动性质 |
|---|---|
| `arch/risc-v/Kconfig` | 新增 ESP32-P4 芯片选项 |
| `arch/risc-v/src/common/espressif/Kconfig` | if 条件 / choice / CHIP_SERIES 三处注册 P4 |
| `arch/risc-v/src/common/Make.defs` | 芯片层构建规则 |
| `arch/risc-v/src/esp32p4/` | 芯片层源码（来自 Apache NuttX） |
| `arch/risc-v/include/esp32p4/` | 芯片层头文件 |

详细排错过程见 `02_阶段2_3-7_BringUp复盘_01_目录搬迁与Kconfig三层注册.md`。

## 验证记录

在基线提交的干净副本上 `git apply --check` 通过。

副本用以下方式导出（**注意**：repo 管理的仓库无法直接 `git clone`，
其 `.git/objects` 是指向 `.repo/project-objects/` 的符号链接）：

```bash
mkdir -p /tmp/nuttx_patchtest
cd <openvela 根目录>/nuttx
git archive dd92bcf425738734d1b8aed09c2bd4dbe3f2e438 | tar -x -C /tmp/nuttx_patchtest
```

---

# 0002-esp-hal-skip-psram-mmu-unmap.patch

## 性质：临时绕行（workaround），非功能补充

与 `0001` 不同——`0001` 补充的是缺失的 P4 支持代码，属于长期需要；
本补丁是绕开一个上游缺陷，**上游修复后应当删除**。

## 目标仓库

`nuttx/arch/risc-v/src/esp32p4/esp-hal-3rdparty`（独立 git 仓库，构建时自动拉取）

- 基线提交：`8d0a898910084206721a0892ab093021bca1496a`
- 与 `arch/risc-v/src/esp32p4/Make.defs` 中的 `ESP_HAL_3RDPARTY_VERSION` 一致

## 解决的问题

启用 PSRAM / 以太网 / SPI Flash 任一功能时，系统在启动早期崩溃：

- 现象一：看门狗 10.3 秒周期复位（LP WDT）
- 现象二：停在异常处理中，串口保持连接但无 NSH 提示符
- 两种现象下串口均无任何输出

## 根因

bootloader_init_ext_mem() bootloader_esp32p4.c:162
→ mmu_hal_init()
→ mmu_hal_unmap_all() components/hal/mmu_hal.c:40
→ mmu_ll_unmap_all(MMU_LL_PSRAM_MMU_ID)
→ REG_WRITE(SPI_MEM_S_MMU_ITEM_INDEX_REG, ...)
地址 = DR_REG_PSRAM_MSPI0_BASE + 0x380 = 0x5008e380
→ PMP Store access fault (mcause=0x30000007, mtval=0x5008e380)
→ exception_common → riscv_doirq
→ 中断上下文尚未建立，空指针二次崩溃 (mtval=0xa8)


**PSRAM MSPI 控制器在此时尚未初始化，写其 MMU 寄存器被 PMP 拒绝。**

ESP-IDF 有二级引导程序负责该控制器的初始化；NuttX 在 P4 上使用 Simple Boot
（`CONFIG_ESPRESSIF_SIMPLE_BOOT=y`），ROM 直接跳转至 NuttX，跳过了这一步。

## 相关上游 issue

espressif/esp-idf#16763（IDFGH-15850）
"ESP32-P4 bootloader sometimes bootloops in mmu_ll_unmap_all"

- 状态：Closed，标签 `Resolution: Done`
- 报告者崩溃地址同为 `0x5008e380`，芯片 revision **v1.0**（本项目为 v3.2）
  → **与芯片修订版无关**
- 报告者为间歇性（约 1/10），本项目为每次必现
  → 推测与 ESP-IDF 有二级引导、NuttX 无二级引导的差异有关

## 局限

本补丁直接注释掉 PSRAM MMU 清空，**在使用 PSRAM 时可能导致残留映射**。
正式方案应为：条件编译，或在调用前先初始化 PSRAM MSPI 控制器。

## 怎么用

```bash
cd <nuttx>/arch/risc-v/src/esp32p4/esp-hal-3rdparty
git apply --check ../../../../../../contest2026_330_neiheyoumuzhe/patches/0002-esp-hal-skip-psram-mmu-unmap.patch
git apply ../../../../../../contest2026_330_neiheyoumuzhe/patches/0002-esp-hal-skip-psram-mmu-unmap.patch
```

相对路径以实际目录结构为准，建议改用绝对路径。

## 验证记录

应用本补丁后，`spiflash` 配置可正常启动，SmartFS 经 `mksmartfs /dev/smart0`
格式化后可挂载、读写、重启后数据持久。

详见 `03_04R_共同根因_MMU初始化PMP异常.md`。

---

# 0003-apps-mbedtls-header-priority.patch

## 性质：构建修复，长期需要

启用 `CONFIG_CRYPTO_MBEDTLS=y` 的 Espressif 目标都需要。
本项目中即：只要开启 ai_agent，就必须打这个补丁。

## 目标仓库

`apps/`（repo 管理的公共仓库）

## 解决的问题

编译在依赖生成阶段失败，报 7 个 `#error`：

apps/crypto/mbedtls/mbedtls/include/mbedtls/check_config.h:119:2:
error: "MBEDTLS_ECJPAKE_C defined, but not all prerequisites"
check_config.h:313: "MBEDTLS_KEY_EXCHANGE_ECDH_RSA_ENABLED ..."
check_config.h:322: "MBEDTLS_KEY_EXCHANGE_ECDHE_PSK_ENABLED ..."
check_config.h:334: "MBEDTLS_KEY_EXCHANGE_ECDHE_RSA_ENABLED ..."
check_config.h:341: "MBEDTLS_KEY_EXCHANGE_ECDHE_ECDSA_ENABLED ..."
check_config.h:904: "MBEDTLS_SSL_DTLS_CONNECTION_ID_COMPAT ..."
check_config.h:1038: "MBEDTLS_SSL_CONTEXT_SERIALIZATION ..."


触发文件为 esp-hal 的 `bootloader_support/src/bootloader_sha.c`。

## 根因

ESP-IDF（esp-hal-3rdparty）与 NuttX 各自带一份 mbedtls fork，
两者的结构体布局与配置符号集合不同。

`apps/crypto/mbedtls/Make.defs` 用 `${INCDIR_PREFIX}`（展开为 `-I`）
加入 NuttX 那份的头文件路径，使其排在所有 `-I` 路径的最前面，
对**每一个**编译单元生效，包括 esp-hal 自己的源文件。

于是 esp-hal 的文件在 ESP-IDF 配置宏生效的情况下，
命中了 NuttX 的 `check_config.h`，逐项校验全部不匹配。

**注意**：这 7 项并非依赖缺失。`ECP_C` / `ECDH_C` / `ECDSA_C` /
`SSL_PROTO_DTLS` 在 `.config` 中均为 `y`，问题纯粹是头文件串台。

## 解法

`-I` → `-isystem`。NuttX 那份仍可被找到，但优先级降到 ESP-IDF 之后，
esp-hal 源文件转而命中自己那份。

与上游脚本 `packages/ai_agent/fix_esp32s3.sh` 的 fix 1 做法一致
（该脚本为 ESP32-S3 上跑 ai_agent 所写，说明这是 Espressif 平台的共性问题）。

## 怎么用

```bash
cd <openvela 根目录>/apps
git apply --check ../contest2026_330_neiheyoumuzhe/patches/0003-apps-mbedtls-header-priority.patch
git apply ../contest2026_330_neiheyoumuzhe/patches/0003-apps-mbedtls-header-priority.patch
```

## 验证记录

打补丁后，上述 7 个 `#error` 全部消失，编译阶段通过。
ESP32-P4，openvela / NuttX 13.0.0，2026-09-13。

---

# 0004-vendor-board-common-espressif.patch

## 性质：构建修复，长期需要

## 目标仓库

`vendor/openvela/`（repo 管理的公共仓库）

## 解决的问题

`boards/common/src/Makefile` 无条件编译 QEMU 板级辅助文件
（`qemu_weakfunc.c`、`qemu_initialize.c`），这两个文件在 Espressif 目标上不存在。

`arch/risc-v/src/board` 是指向该目录的符号链接，因此每次构建本赛题板子
都会拉入错误的源文件。

## 解法

改为 include 板级公共 `Make.defs`，并在 `CONFIG_ESPRESSIF_SPIFLASH=y` 时
加入 `esp_board_spiflash.c`。

## 怎么用

```bash
cd <openvela 根目录>/vendor/openvela
git apply --check ../../contest2026_330_neiheyoumuzhe/patches/0004-vendor-board-common-espressif.patch
git apply ../../contest2026_330_neiheyoumuzhe/patches/0004-vendor-board-common-espressif.patch
```

## 验证记录

ESP32-P4，openvela / NuttX 13.0.0。该改动自 2026-08-20 起持续生效，
本项目所有成功构建均基于它。
