# 证据目录

板上实测的原始日志与统计。文档中的每个数字都能在这里找到出处。

## 2026-09-18

### ELF 动态加载

| 文件 | 内容 |
|---|---|
| `elf-loading-7tests-pass.log` | `elf` 示例七个测试全部通过的完整输出（4KB）。补丁 0013 + 0014 的验收记录。 |
| `elf-dynamic-loading-success.log` | 同一轮的详细日志（800KB），开启了 `CONFIG_DEBUG_BINFMT`。包含每一条重定位的地址与结果、加载后代码段前 16 字节的 dump、PMP 寄存器的实际值。定位过程的原始材料。 |

读这两份的顺序：先看小的确认结果，需要追细节时再翻大的。

**关键行**

- `Child: execv was successful!` — 模块内再次 exec 成功
- `Memory Usage End-of-Test: Change: 0` — 加载与卸载的内存收支归零
- `PMP06 cfg=8f R1 W1 X1` — 修复后堆区可执行（修复前为 `cfg=8b X0`）
- `TEXT at 4ff72980: 41 11 05 45 ...` — 内存内容与主机 objdump 逐字节一致

### L3 心跳定时自诊断

| 文件 | 内容 |
|---|---|
| `l3-heartbeat-114rounds.log` | 连续运行 114 次心跳触发的完整日志 |
| `l3-heartbeat-42rounds.log` | 早期的一段，`l3-regression-summary.md` 引用的就是它 |
| `l3-regression-summary.md` | 统计与分析 |
| `regression.png` | 三张图：每轮耗时、单轮内请求体增长、跨轮首次请求大小 |

**注意**：114 轮中只有 53 轮真正执行了诊断。其余轮次命中了
LLM 响应缓存，`llm_ms=0`、`tools=0`，任务并未运行——定时任务
每次发送的提示词相同，一旦有一轮的回复进入缓存，之后每次触发
都直接返回它。该缺陷已修复（system 通道不查缓存），修复后的
数据另行采集。

## 复现方式

日志由 picocom 记录：

```bash
picocom -b 115200 --omap delbs --logfile <文件> /dev/ttyACM0
```

固件构建见仓库根目录的构建说明，补丁应用方式见 `patches/README.md`。

## 统计脚本

- `tools/parse_regression.py <日志>` — 逐轮提取状态、耗时、工具调用数、请求体大小，输出到 `/tmp/rounds.json`
- `tools/plot_regression.py` — 读取该 json 绘图

两者需要 matplotlib，装在系统 Python 下即可，与编译固件用的
虚拟环境无关。
