# B2 链接失败诊断：cJSON 版本漂移（2026-11-25）

B2（全部 32 个补丁 + defconfig 配置，/tmp/rb-b2）编译通过（B1 的两处
错误均消失），但链接失败：

```
/tmp/rb-b2/packages/ai_agent/src/tools/tool_media.c:1216:
(.text.tool_music_search_execute+0x2ee): undefined reference to
`cJSON_GetNumberValue'
```

## 根因

**cJSON 源码不在 git 里，两棵树实际用的是不同版本。**

1. `apps/netutils/cjson/.gitignore` 忽略 `/cJSON*`——解包目录不入库，
   由 Makefile 在目录缺失时下载：`CONFIG_NETUTILS_CJSON_URL` +
   `CONFIG_NETUTILS_CJSON_VERSION`（Kconfig 默认 1.7.12，siliconloop
   defconfig 只写 `CONFIG_NETUTILS_CJSON=y`，两个 .config 均为
   `"1.7.12"`）。
2. 工作区 `apps/netutils/cjson/cJSON/` 是 **2026-08-16 遗留的 1.7.15
   解包**（stat 证实），Makefile 见目录存在就不再下载，于是工作区
   一直是"配置说 1.7.12、实际编 1.7.15"的漂移状态。1.7.15 有
   `cJSON_GetNumberValue`（cJSON.c:124，编译出的 .o 有该 T 符号，
   apps/include/netutils/cJSON.h 也是 1.7.15、带声明）。
3. rb-b2 干净树老实按配置下载了 1.7.12（构建日志 `Downloading:
   v1.7.12.tar.gz`）：该版本 cJSON.c 0 处出现该函数、cJSON.h 无声明
   （tool_media.c:1221 因此有 implicit-declaration 告警，构建日志
   行 144），.o 里无符号 → 链接失败。

调用方 `tool_media.c:1221` 的使用是 ai_agent 基线自带的（补丁集无一
触碰 tool_media.c），不是本次补丁引入。

## 与工作区逐项比对（排除其他嫌疑）

- 工作区 apps 未提交改动只有两处：`crypto/mbedtls/Make.defs`
  （-isystem，= 已导出的 0003）、
  `crypto/mbedtls/include/mbedtls/mbedtls_config.h`（OUT_CONTENT_LEN
  clamp，= 已导出的 0028）。rb-b2 均已打对应补丁，两边一致。
- 两个 .config 的 cJSON 相关行完全相同（NETUTILS_CJSON=y，版本
  "1.7.12"）。
- 工作区最终 nuttx 里 5 个 cJSON_Get* T 符号齐全（nm 证实），
  其中 GetNumberValue 只能来自 1.7.15 解包。

## 处置

把工作区 1.7.15 解包目录复制进 rb-b2（删除 1.7.12 tarball 防重解包、
删 apps/include 旧头让 context 重拷、删旧 .o 强制重编），继续链接。
这验证"补丁集补齐后唯一缺口是这处环境漂移"。

## 遗留问题（待 Ghee 决定）

干净重建要可复现，cJSON 版本必须钉死。两个选项：

- A. defconfig/补丁加一行 `CONFIG_NETUTILS_CJSON_VERSION="1.7.15"`，
  让配置与实际使用一致（tool_media.c 依赖 1.7.15 的
  GetNumberValue，降级 1.7.12 会破坏功能）。
- B. 保持 1.7.12 并把 tool_media.c 改为 1.7.12 可用写法（用
  cJSON_IsNumber + item->valuedouble，但 valuedouble 字段两版本
  布局需核对）。

A 改动一行、风险低；B 改 ai_agent 源码、需新补丁。建议 A。
工作区的漂移解包本身也应更新到与配置一致的版本或钉版本。
