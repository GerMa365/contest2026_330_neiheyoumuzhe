# SiliconLoop 演示视频脚本（5 分钟）

## 总体说明

- 录制工具：picocom，115200 8N1
- 串口设备：/dev/ttyACM0
- 录制命令：`picocom -b 115200 --omap delbs --logfile video-raw.log /dev/ttyACM0`
- 后期需要：剪掉等待间隙、加速诊断过程、用字幕标注关键日志行
- 串口输出会交错（agent 输出和 nsh 提示符互相覆盖），后期用字幕覆盖或剪掉乱序部分

---

## 第一段：问题——mock 测不出的故障（30 秒）

### 画面

屏幕左侧放代码，右侧放板子特写（或串口终端）。

### 旁白

> 这段代码有一个 bug：
>
> ```c
> while (!fifo_has_space())
>     usleep(1000);
> fifo_put(g_produced++);
> ```
>
> 生产者等 FIFO 有空间后写入。问题是：如果消费者停止消费，FIFO 填满，这个循环就永远不会退出。
>
> 但 mock 测试发现不了它。mock 里 `fifo_has_space()` 恒为真——没有真实的 FIFO，没有真实的容量限制，测试永远通过。
>
> 只有在真机上，FIFO 真的会满，循环真的会卡死。
>
> SiliconLoop 要解决的问题是：怎么让 AI Agent 在板上自动发现这类故障？

### 需要的画面

- [ ] 代码高亮 `while (!fifo_has_space())` 这几行
- [ ] 可选：终端跑一下 `buggy_app stall`，展示 FIFO 逐渐填满（count 从 0 到 64）

---

## 第二段：Agent 自主诊断（2 分钟）

### 板上操作

```bash
nsh> buggy_app &
nsh> ai_agent
```

等待心跳自动触发（每 120 秒一轮）。为节省录制时间，启动后立即手动催一次：

```bash
nsh> heartbeat_trigger
```

### 旁白

> 启动 buggy_app，它在后台持续生产数据，消费者正常消费，每生产 50 个写一次心跳文件。
>
> 启动 AI Agent。它初始化完成后进入待命，每 120 秒自动执行一次心跳诊断。
>
> 我手动触发一次心跳，加速演示。
>
> Agent 开始执行七步诊断：
> 1. 读取 HEARTBEAT.md，获取本轮任务
> 2. 读取 self-diagnostic.md，加载诊断 Skill
> 3. 第一次读心跳文件，采样当前值
> 4. 执行 `ps`，查看进程列表
> 5. 执行 `free`，查看堆状态
> 6. 第二次读心跳文件，再次采样
> 7. 写报告到 /data/ai_agent/evidence/report.md
>
> 注意：全程无人干预。Agent 自己读文件、执行命令、写报告。
>
> 报告里有四段：观察到的证据、假设、建议、置信度。
>
> 关键判据是两次心跳读数的差值。从 10900 到 10950，增加了 50——任务在前进，系统健康。

### 需要特写的日志行

按出现顺序，后期用字幕或高亮标注：

```
[trace] BEGIN chat=heartbeat chan=system
```
→ 心跳触发起点

```
[agent] Tool call: read_file args={"path": "/data/ai_agent/evidence/heartbeat.txt"}
```
→ 第一次采样

```
[agent] Tool call: run_shell args={"command": "ps"}
```
→ 进程列表

```
[agent] Tool call: run_shell args={"command": "free"}
```
→ 堆状态

```
[agent] Tool call: read_file args={"path": "/data/ai_agent/evidence/heartbeat.txt"}
```
→ 第二次采样

```
[agent] Tool call: write_file args={"path": "/data/ai_agent/evidence/report.md", ...}
```
→ 报告落盘

```
[trace] END status=ok iters=7 tools=7 llm_ms=... elapsed=...s
```
→ 本轮完成

### 后期处理

- 等待 TLS 握手和 LLM 响应的时间（各 10-30 秒）用 4x-8x 加速
- 在加速段上方加字幕"等待 LLM 响应..."
- 七步执行过程保持原速或 2x 加速

---

## 第三段：故障注入对照（1 分 30 秒）

### 板上操作

先确保上一轮 ai_agent 还在运行（或重新启动）：

```bash
nsh> buggy_app stall &
nsh> heartbeat_trigger
```

或者用交互方式让 Agent 手动诊断：

```bash
nsh> ask diagnose the device
```

### 旁白

> 现在注入故障。`buggy_app stall` 停止消费者，FIFO 逐渐填满，生产者卡在等待循环里。
>
> 触发下一轮诊断。同一个 Skill，同一套七步流程。
>
> 看关键区别：两次心跳读数。
>
> 正常情况下，心跳值会递增——10900 到 10950，说明任务在前进。
>
> 故障情况下，心跳值不变——50 到 50。两次读数相同，说明任务卡住了，没有产出新的心跳。
>
> Agent 的报告从"healthy"变成了"stall detected"。同样的流程，不同的结论。
>
> 这就是判据的有效性：心跳增量是唯一无歧义的指标。`ps` 看到的任务数在两种情况下相同——buggy_app 的生产者和消费者始终是两个线程，无法据此区分。

### 需要特写的日志行

**正常轮次（对比用，可从第二段的录制中取）：**

```
[agent] Tool call: read_file args={"path": "/data/ai_agent/evidence/heartbeat.txt"}
...（两次采样）...
Heartbeat counter: 10900 → 10950
```

**故障轮次：**

```
[agent] Tool call: read_file args={"path": "/data/ai_agent/evidence/heartbeat.txt"}
...（两次采样）...
Heartbeat counter: 50 → 50
```

**报告内容对比（后期并排或切换展示）：**

| 正常 | 故障 |
|---|---|
| "Heartbeat counter advanced, task is alive" | "Heartbeat counter unchanged, task appears stalled" |
| 置信度：高 | 置信度：高 |

### 后期处理

- 左右分屏或快速切换，对比两次诊断的关键差异
- 用箭头或高亮标注心跳读数的变化

---

## 第四段：ELF 动态加载（1 分钟）

### 板上操作

```bash
nsh> elf
```

### 旁白

> 最后展示 ELF 动态加载。
>
> ESP32-P4 之前在 openvela 上不支持加载 ELF 模块。我们补了两个补丁解决了这个问题。
>
> 运行 `elf` 测试。它会加载七个测试模块，逐个执行。
>
> 全部通过。
>
> 这背后有两层根因：
>
> 第一层是 PMP 权限。ESP32-P4 的内存保护单元把堆区设为"可读写、不可执行"，ELF 代码加载到堆上后，第一条指令就触发取指异常。我们在板上 dump 了 PMP 寄存器，确认了权限位，修改后解决。
>
> 第二层是缓存一致性。代码经数据通路写入，但取指走另一条通路。ESP32-P4 的 L1 缓存是写回模式，重定位后的代码留在 d-cache 里，i-cache 读到的是旧字节。实测 `fence.i` 单独不够，需要显式写回 d-cache 再失效 i-cache。

### 需要特写的日志行

```
Initial memory usage: 84984
```
→ 测试开始

```
****************************************************************************
* Executing errno
****************************************************************************
```
→ 每个测试的标题

```
Hello, World on stdout
```
→ errno 测试的输出

```
Memory Usage End-of-Test: Change: 0
```
→ 每个测试结束后内存收支归零（出现 7 次）

```
****************************************************************************
* Executing task
****************************************************************************
```
→ 最后一个测试

```
Child: execv was successful!
```
→ 模块内再次 exec 成功

### 后期处理

- 七个测试可以 2x-4x 加速，只保留每个测试的标题和 "Change: 0"
- 最后一个测试（task）保持原速，展示 execv 成功

---

## 结尾（10 秒）

### 旁白

> SiliconLoop，在 ESP32-P4 上让 AI Agent 自主诊断硬件故障。
>
> 谢谢。

### 画面

- 板子特写，串口终端显示 nsh 提示符
- 可选：再跑一次 `heartbeat_trigger`，展示 Agent 持续运行

---

## 录制检查清单

录制前：

- [ ] 板子已烧录 siliconloop 固件
- [ ] 以太网已连接，IP 配置正确（192.168.3.200）
- [ ] `include/agent_secrets.h` 已配置 LLM 密钥
- [ ] picocom 已启动并带 `--logfile`
- [ ] 之前的 buggy_app 和 ai_agent 已停止（`killall buggy_app`，重启板子）

录制顺序：

1. 开 picocom
2. `buggy_app &` → `ai_agent` → 等待启动完成 → `heartbeat_trigger` → 等待诊断完成（第二段素材）
3. `buggy_app stall &` → `heartbeat_trigger` → 等待诊断完成（第三段素材）
4. 重启板子 → `elf`（第四段素材）
5. 关 picocom

后期：

- [ ] 剪掉等待间隙和串口乱序
- [ ] 加速 LLM 响应等待段
- [ ] 添加字幕标注关键日志行
- [ ] 分屏对比正常/故障诊断结果
- [ ] 总时长控制在 5 分钟内
