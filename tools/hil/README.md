# tools/hil — 硬件在环（HIL）脚本

对板子（ESP32-P4，串口 `/dev/ttyACM0`）的全部操作都从这里走。
串口一次只能被一个进程打开；**烧录用 `flash.sh`（只写 0x2000），
测试观察用 `boardtest.py`，两者不要同时跑**。

## 脚本清单

| 脚本 | 用途 |
| --- | --- |
| `flash.sh` | 烧录固件（内部调 `/home/w/esp-venv/bin/esptool`，需 PATH 前置 `/home/w/esp-venv/bin`） |
| `find_port.py` | 按 USB ID 定位串口设备名（ttyACM 编号会漂移） |
| `serial_run.py` | 一次性命令会话：复位/等 nsh/发命令/存日志；`Link` 类抗 USB 重枚举，被其他脚本复用 |
| `boardtest.py` | **板测主入口（2026-11-24 起）**：单进程从硬复位起独占串口、全部字节连续落 raw；冷启动固定 `buggy_app &` → 等 `buggy_app: producing` → 起 agent →（`--push`）推包 → 观察 N 轮 |
| `logcheck.py` | **日志完整性检查**：BEGIN/END 配对、iter 连续、LLM 调用-结果配对、每轮 memprobe；缺口标红，违规即退出码 1 |
| `push_hotfix.py` | 独立推包 CLI（`--chunk 252` 已定；`--pace` 默认 0.05，0.02 待板测，依据见下） |
| `serial_tee.py` | PTY 桥接共享串口（录屏演示用），把板子字节镜像进日志 |
| `scenario.py` / `regression.sh` / `bg.sh` | 长回归编排（nohup 后台跑） |

## boardtest.py 用法

```bash
# A 段（不推包）：冷启动 + buggy_app + agent + 3 轮观察
/home/w/esp-venv/bin/python3 tools/hil/boardtest.py --raw /tmp/a.raw cold
# B 段（修复包常驻）：同上 + 进程内推包（不再单独跑 push_hotfix.py）
/home/w/esp-venv/bin/python3 tools/hil/boardtest.py --raw /tmp/b.raw cold --push
```

- **串口单记录进程**：推包在 boardtest 进程内完成，运行期间不得另开
  `serial.Serial()`（2026-11-24 教训：脚本+内联观察器混用，字节丢失）。
- **冷启动门禁**：等不到 `buggy_app: producing, heartbeat at …` 即判该次
  冷启动无效（rc=10）——buggy_app 是 heartbeat.txt 的唯一写入者，缺它
  的轮次不能作为验收证据。
- 退出码：0 成功；2 无串口；5 无 nsh；6 轮超时；7 agent 启动失败；
  8 推包门失败；9 停止条件命中（崩溃/处置动作等）；10 冷启动无效。

## logcheck.py 用法（离线，不碰板子）

```bash
/home/w/esp-venv/bin/python3 tools/hil/logcheck.py <raw.log> [more.raw ...]
```

检查项：`MISSING_END`（有 BEGIN 无 END）、`ORPHAN_END`（BEGIN 未捕获，
附着太晚的签名）、`ITER_GAP`（iter 编号不连续）、`LLM_NO_RESULT`（LLM
请求无 Response 行）、`NO_MEMPROBE`（整轮无内存打点）、`TRAILING_LLM_REQ`
（日志截断在半轮）。违规行标红，`TOTAL violations` 为 0 才算日志完整。

## 推包默认值依据（--chunk 252，--pace 暂回 0.05）

- 板侧三道约束：UART RX 环 256 B（`nsh_commands.c` fwpush 流程），
  行缓冲 `line[1024]`，解码上限 `FWPUSH_CHUNK 512`（=684 个 b64 字符）。
- 252 是 4 的倍数，252 字符 + `\n` ≤ 256 B，一次写不溢 RX 环；
  6,388 B ELF → 8,520 b64 字符 → 34 行。
- **逐行 ack 前提（2026-11-25 补记）**：脚本每发一行只做固定 `drain(0.1)`
  再发下一行，**不等板子逐行回 ack**。"252+换行 ≤ 256 B 不溢 RX 环"
  的前提是：每一行开始发送时，板子已经把上一行从 RX 环读走（回环 echo
  的字节被 drain 吸收）。若板子在 RX 环 256 B 装满前没读走数据（如恰逢
  控制台忙），快推仍可能丢字节——这是 pace 不能无限缩小的根本原因。
- **pace 节奏（C1/C2 约定，2026-11-25）**：`--pace` 默认回退为
  **0.05**（2026-11-08 起板上多次成功验证的值）。0.02（34 行 ≈ 5–7 s，
  可赶在首次 120 s 心跳前）**尚未上板验证**：第一次板测先用
  chunk 252 / pace 0.05，FNV-1a 通过并记录耗时后，再单独测 0.02。
- 安静窗逻辑与全部校验门（fwpush 探测、板侧 OK、FNV-1a）保持不变。

## 证据脚本归属

`docs/evidence/<日期>/` 下的历史 `.py` 是当次板测的现场脚本，
**只读保留、不删不改**（补丁红线 5）；新板测一律用 `boardtest.py`。
