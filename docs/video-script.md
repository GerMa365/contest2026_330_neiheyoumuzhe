# SiliconLoop 演示视频脚本（5 分钟）

## 总体说明

- 录制工具：picocom，115200 8N1，设备 `/dev/ttyACM0`
- 录制命令：`picocom -b 115200 --omap delbs --logfile video-raw.log /dev/ttyACM0`
- 后期：剪掉等待间隙、2x 加速 LLM 等待段、字幕标注关键日志行
- 串口输出会交错（Agent 的输出和提示符互相覆盖），后期用字幕覆盖或剪掉
- 录制中会出现 `emac_stack_input: ERROR: emac RX netpkt_alloc failed`，
  这是以太网收包时缓冲区一时不够，TCP 会重传，不影响功能。
  后期字幕说明或剪掉

### 两个提示符

板上有两层命令环境，不能混用：

| 提示符 | 环境 | 常用命令 |
|---|---|---|
| `nsh>` | NuttX Shell | `buggy_app`、`elf`、`ps`、`free`、`reboot` |
| `vela>` | AI Agent | `heartbeat_trigger`、`ask`、`heap_info`、`help`、`quit` |

`ai_agent` 在 `nsh>` 下启动，启动完成后出现 `vela>`。

**关键限制：Agent 运行期间无法回到 `nsh>`。** 要执行 NSH 命令必须先
`vela> quit`，或者重启板子。这决定了第二段和第三段之间必须重启。

### 三段素材要分三次录

| 素材 | 前置状态 |
|---|---|
| 第二段（正常） | 重启 → `buggy_app &` → `ai_agent` |
| 第三段（故障） | **重启** → `buggy_app stall &` → `ai_agent` |
| 第四段（ELF） | 重启 → `elf` |

第二段和第三段之间**必须重启**，否则会有两个 `buggy_app` 同时写心跳
文件，正常那个仍在递增，故障判定失效。

---

## 第一段：问题——mock 测不出的故障（30 秒）

### 画面

屏幕左侧代码，右侧板子特写或串口终端。

### 旁白

> 这段代码有一个 bug。
>
> ```c
> while (!fifo_has_space())
>     usleep(1000);
> fifo_put(g_produced++);
> ```
>
> 生产者等 FIFO 有空间再写入。如果消费者停止消费，FIFO 填满，
> 这个循环永远不会退出。
>
> 但 mock 测试发现不了它。mock 里没有真实的 FIFO，
> `fifo_has_space()` 恒为真，测试永远通过。
>
> 只有在真机上，FIFO 真的会满，循环真的会卡死。而且它不崩溃、
> 不报错，只是不动了。
> 但要说清楚：正常情况下 FIFO 也会填满。生产者每 10 毫秒放一个，
> 消费者每 20 毫秒取一个，生产比消费快一倍。满了之后生产者会等，
> 消费者不断取走腾出空间，整个系统被拖慢到消费者的速度，但一直
> 在前进。
>
> 故障不是「FIFO 满了」，而是「满了之后再也不会空」。
>
> SiliconLoop 要解决的问题是：怎么让 AI Agent 在板上自己发现
> 这类故障。

### 画面要点

- 代码高亮 `while (!fifo_has_space())`
- 不展示 ps——要展示卡死状态必须先启动 buggy_app stall，会打乱
  录制顺序。ps 的对比放在第三段效果更好

---

## 第二段：Agent 自主诊断（2 分钟）

### 板上操作

```
nsh> ifconfig
```

确认 `eth0 ... RUNNING`。

```
nsh> buggy_app &
```

后台任务的打印会挤掉提示符，**按一次回车恢复**。

```
nsh> ai_agent
```

等待启动完成，出现 `vela>`。为节省录制时间手动触发一次：

```
vela> heartbeat_trigger
```

### 旁白

> 启动 buggy_app。它在后台持续生产数据，消费者正常消费，
> 每生产 50 个写一次心跳计数。
>
> 启动 AI Agent。它每 120 秒被心跳服务自动唤醒一次。这里手动
> 触发一次，省去等待。
>
> Agent 开始执行七步诊断：
> 读取任务清单、载入诊断 Skill、第一次采样心跳、执行 ps、
> 执行 free、第二次采样心跳、写报告。
>
> 全程无人干预。它自己读文件、自己执行命令、自己写报告。
>
> 两次采样之间隔着 ps 和 free 两条命令，十几秒的间隔是自然拉开
> 的，不依赖 Agent 主动等待——它没有 sleep 这个工具。
>
> 判据是两次心跳读数的增量。数字在涨，说明任务在前进。

### 需要特写的日志行

```
[heartbeat] Triggered agent check
[trace:...] BEGIN chat=heartbeat chan=system
```
→ 心跳触发，注意 `chan=system` 表示不是人发起的

```
[agent] Tool call: read_file args={"path": ".../heartbeat.txt"}
```
→ 第一次采样（第 3 步）

```
[agent] Tool call: run_shell args={"command": "ps"}
[agent] Tool call: run_shell args={"command": "free"}
```
→ 取证，同时拉开采样间隔

```
[agent] Tool call: read_file args={"path": ".../heartbeat.txt"}
```
→ 第二次采样（第 6 步）

```
[agent] Tool call: write_file args={"path": ".../report.md", "content": "..."}
```
→ 报告落盘，`content` 里能看到两次读数和四段式结论

```
[trace:...] END status=ok iters=7 tools=7
```
→ 七步七工具，完整执行

### 录制记录

录完把实际数字填进来，后期字幕用：

- 第一次心跳读数：______
- 第二次心跳读数：______
- 单轮耗时：______ 秒

### 后期处理

- 实测单步 2-3 秒，整轮 15-20 秒，节奏较快
- TLS 握手和 LLM 等待间隙 2x 加速，加字幕「等待 LLM 响应」
- 七步执行保持原速
---

## 第三段：故障注入对照（1 分 30 秒）

### 板上操作

**必须先重启**，否则上一轮的 `buggy_app` 仍在递增心跳：

```
nsh> reboot
```

等待重启完成（picocom 可能断开，断了就重连）。

```
nsh> ifconfig
nsh> buggy_app stall &
```

**按一次回车恢复提示符**。注意这次的输出多一行：

```
buggy_app: consumer disabled, FIFO will fill up
```

```
nsh> ai_agent
vela> heartbeat_trigger
```

### 旁白

> 现在注入故障。`buggy_app stall` 关掉消费者，FIFO 一秒内填满，
> 生产者卡在等待循环里，心跳不再更新。
>
> 同一个 Skill，同一套七步流程，什么都没改。
>
> 两次采样的读数相同。任务停止前进。
>
> Agent 的结论从健康变成了卡死。
>
> 这就是判据的价值。ps 看到的任务数在两种状态下完全相同——
> buggy_app 的生产者和消费者始终是两个线程，从进程列表看不出
> 任何异常。心跳增量是唯一无歧义的指标。

### 需要特写的日志行

```
buggy_app: consumer disabled, FIFO will fill up
```
→ 故障注入的证据

```
[agent] Tool call: read_file args={"path": ".../heartbeat.txt"}
```
→ 两次采样，读数相同

```
[agent] Tool call: write_file args={"path": ".../report.md", "content": "..."}
```
→ 报告内容里应出现 stall / 停止前进之类的判定

### 录制记录

- 第一次心跳读数：______
- 第二次心跳读数：______（应与上一行相同）
- Agent 的判定文字：______

### 后期处理

- 与第二段并排分屏，或快速切换对比
- 高亮两次读数——正常那边数字不同，故障这边数字相同
- 两段的 `ps` 输出可以并排，展示它们看起来一模一样

---

## 第四段：ELF 动态加载（1 分钟）

### 板上操作

```
nsh> reboot
```

重启后直接运行，不需要启动 Agent：

```
nsh> elf
```

### 旁白

> 最后是 ELF 动态加载。
>
> ESP32-P4 此前在 openvela 上无法执行编译期之外的程序。
>
> 运行 elf 测试，它加载七个模块依次执行。全部通过，而且每个测试
> 结束后内存收支归零——加载和卸载都是干净的。
>
> 这背后是两层根因。
>
> 第一层是内存保护。PMP 把堆区设成可读写、不可执行，模块代码
> 加载到堆上，第一条指令就取不出来。我们在板上把 PMP 寄存器
> dump 出来，确认那一条规则的执行位是 0。
>
> 第二层是缓存。代码是通过数据通路写进去的，取指走另一条通路，
> 而这颗芯片的 L1 缓存是写回模式——代码还在数据缓存里，取指侧
> 读到的是旧字节。我们把加载后的内存 dump 出来，和主机上的
> objdump 逐字节比对，证明内存内容是对的，问题只能在取指路径。
>
> 实测 fence.i 单独不够，它排序访存与取指，不负责刷出写回缓存。

### 需要特写的日志行

```
Mounting ROMFS filesystem at target=/mnt/elf/romfs
```
→ 测试模块所在的文件系统

```
****************************************************************************
* Executing errno
****************************************************************************
```
→ 每个测试的标题，共七个

```
Hello, World on stdout
Hello, world!
In dummyfunc() -- PASS
Child: execv was successful!
```
→ 各模块的实际输出，证明代码真的在执行

```
Memory Usage End-of-Test:
  Before:    90096 After:    90096 Change:        0
```
→ 收支归零

### 后期处理

- 七个测试 2x-4x 加速，保留每个标题
- `task` 是最后一个，保持原速——它在模块内又 exec 了另一个模块

---

## 结尾（10 秒）

### 旁白

> SiliconLoop：在 404KB 堆的 ESP32-P4 上，让 AI Agent 自己发现
> 硬件故障。

### 画面

板子特写，串口显示 `vela>` 提示符。

---

## 录制前检查

按顺序执行，**每一项都要确认**：

```
nsh> reboot
```

重连串口后：

```
nsh> ifconfig
```
- [ ] `eth0 ... RUNNING`，IP 为 192.168.3.200

```
nsh> ai_agent
```
- [ ] 启动日志跑完，出现 `vela>`
- [ ] 日志中有 `[ws] WebSocket server started`（说明网络服务全起来了）

```
vela> heap_info
```
- [ ] 空闲 ≥ 110KB

> 长时间运行后堆碎片化会导致 TLS 握手失败
> （`[vela_tls] ssl_setup ret=0x7f00`）。实测跑一百多轮后空闲降到
> 34KB，`net_test` 和 LLM 调用全部失败。**录制前必须重启。**

```
vela> heartbeat_trigger
```
- [ ] 能看到 `Handshake OK` 而不是 `ssl_setup ret=0x7f00`
- [ ] 七步跑完，`END status=ok iters=7 tools=7`

确认无误后：

```
vela> quit
nsh> reboot
```

**从干净状态开始正式录制。**

## 录制顺序

| # | 操作 | 素材 |
|---|---|---|
| 1 | 开 picocom（带 `--logfile`） | — |
| 2 | `nsh> buggy_app &` → 回车 → `nsh> ai_agent` → `vela> heartbeat_trigger` | 第二段 |
| 3 | `vela> quit` → `nsh> reboot` → 重连 | — |
| 4 | `nsh> buggy_app stall &` → 回车 → `nsh> ai_agent` → `vela> heartbeat_trigger` | 第三段 |
| 5 | `vela> quit` → `nsh> reboot` → 重连 | — |
| 6 | `nsh> elf` | 第四段 |
| 7 | 关 picocom，保存 `video-raw.log` | — |

## 后期清单

- [ ] 剪掉重启和重连的间隙
- [ ] LLM 等待段 2x 加速
- [ ] 字幕标注上述关键日志行
- [ ] 第二段与第三段的心跳读数并排对比
- [ ] 把实际录到的数字填进上面的「录制记录」
- [ ] 总时长 ≤ 5 分钟
