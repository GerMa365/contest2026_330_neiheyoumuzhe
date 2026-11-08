# M4 板上 smoke 记录（进行中，2026-11-08）

## 已完成项

| 项 | 结果 | 证据 |
|---|---|---|
| M4 固件启动 | NuttX dd92bcf4257-dirty Nov 8 2026 06:13:13，nsh 正常，maxfree 280,200 | m4-smoke2-boot.log |
| fwpush 正例 | `fwpush: OK 6388 bytes, fnv1a=df9dc4f8 -> /data/ai_agent/patches/buggy_app_fixed`（路径修复生效：落在 L3 加载路径） | m4-smoke2-push-OK.log |
| fwpush 负例① 截断包 | 拒绝：`fwpush: size mismatch got=3000 want=6388`，payload 已 unlink | （本文档内引述，串口转录见会话日志） |
| fwpush 负例② 坏校验包 | 见下方"传输竞争"一节 | 待补 |

## 传输竞争（fwpush 可靠性，未入固件缺陷清单）

nsh 与 ai_agent 的 vela CLI **同时**在 stdin 上 read 同一 UART，输入行
按读到的先后被其中一个吞掉：

1. 头部行 `fwpush <n> <fnv1a>` 被 nsh 抢走 → 后续 base64 块全部被
   vela dispatch 拒为 Unknown command（06:43、07:0x 两次）。
2. 传输中途一块被拆成两半（前缀 'a' 单独成行）→ `fwpush: bad chunk
   (n=-1, got=2904)` → payload unlink（06:50–06:55 三次，pace 无关）。

宿主侧已修 push_hotfix.py（HIL 工具，非固件）：
- 先发裸 `fwpush` 探针，确认 usage 回显来自 vela CLI 再发头部；
- 改用 `\n` 行尾、流式 drain、中途即时检测 `fwpush:`/`Unknown`；
- scenario.py 对 C 轮 push 加 3 次重试（板上失败即 unlink，重试安全）。

07:05 一次完整成功（正例）；07:2x 重试实验仍在进行（见 NEG2 记录）。

## 待办

- NEG2（声明错误校验和 → 板上 readback 比对失败 → CHECKSUM
  MISMATCH + unlink）捕获重跑中
- 负例结论落证据文件
- C r1 起按 Ghee 要求逐轮标注 L2 分支（path / builtin / n-a）：
  M4 固件上 /data/ai_agent/bin/buggy_app 不存在（无部署步骤），
  L2 必走内建回退分支，从"无 spawn 错误 + L2 后 Δ>0"推断并在
  汇总表注明推断依据

## 传输竞争根因补充（07:35）

第 3 次 mid-stream 失败（got=3768，与之前 2904 不同偏移）与抓包对照后
定位：**失败全部发生在心跳 LLM 轮运行期间**（抓包里一轮完整 LLM 诊断
与 base64 流交错，llm_ms=120200——该轮 120 秒才结束）。推论：轮运行
期间 vela CLI 线程长时间不被调度/被 stdout 锁阻塞，256B UART RX 环
无人读取而溢出，块字节丢失 → `bad chunk (n=-1)`。

对策（全部宿主侧，固件不动）：
- push_hotfix.py 增加静默窗口等待（无 `[llm] OpenAI API` 活动 8s 才
  开传；最多等 150s）；
- 精确化拒绝检测（`Unknown command: <本行>` / `nsh: ... not found`，
  不再匹配 agent 报告文本里的 "file not found"——07:28 的抓包里检测器
  被报告内容误触发）；
- mid-stream 出现任何 `fwpush:` 判定行立即停发并收取判定；
- scenario.py C 轮 push 重试 3 次（板上失败即 unlink，重试安全）。

成功路径复现于 07:05（正例）；静默窗口版待 NEG2 重跑后随 C r1 验证。

给 Ghee 的可选项（0024 可一并做，需重烧）：cmd_fwpush 收到头部时先回
一行 ack（如 `fwpush: start`），宿主即可确认"已被 vela CLI 接管"，竞争
检测从启发式变确定性。

## fwpush 负例② 结论（07:37，通过）

声明错误校验和（df9dd6cc）+ 正确 payload 字节 → 板上 readback 计算
fnv1a=df9dc4f8 与声明不符：

```
fwpush: CHECKSUM MISMATCH rlen=6388 sum=df9dc4f8 want=df9dd6cc - payload deleted
```

payload 已删除，回到 vela> 提示符，无崩溃。静默窗口逻辑下传输一次
跑完 267 块无丢块（verdict 在第 266 块后出现）。证据：
m4-smoke2-push-neg2-badsum.log

## smoke 清单完结

| 项 | 结果 |
|---|---|
| 启动检查 | PASS |
| fwpush 正例 | PASS（OK 6388B → L3 路径） |
| fwpush 负例① 截断 | PASS（size mismatch + unlink） |
| fwpush 负例② 坏校验和 | PASS（CHECKSUM MISMATCH + unlink） |

下一步：C r1（--judge m4 --push-hotfix）。

## C r1 失败 → 根因定位 → 固件修复（08:14，待 Ghee 确认烧录）

C r1 判定 fail（cause=net_llm，8 轮心跳全部 LLM 失败，0 次 llm=ok）。
复现实验（无 push，仅 buggy_app bug & + ai_agent）重现同一失败：
`ssl_handshake ret=-0x2880: X509 - Allocation of memory failed`。

### 根因链

1. M4 固件比 M3 多用 ~12.6KB 堆（fwpush 的 16KB 静态 readback 缓冲
   rb.0 是大头，System.map 实证：4ff533f0 00004000 b rb.0）；
2. buggy_app（任务 4KB + pthread 2KB + 杂项 ≈ 8KB）再切走一块，
   agent 启动后 free heap 120,280（smoke 无 buggy_app 时 128,216，
   M3 同场景 140,800）；
3. mbedtls X509 证书解析需要一块大连续内存，120K 布局下分配失败，
   每一轮 LLM 请求在握手即死——**A/B/C 全部场景都跑不了**。

### 修复（nsh_commands.c，已编译通过、host 测试全绿、未烧录）

- 删除 16KB 静态 rb.0；写入时流式累计 FNV（fwpush_fnv1a_upd），
  校验改为 512B 分块重读流式比对——"校验所存即所发"语义不变，
  不再整包驻留 RAM。
- 新固件：920,616 B，sha256
  99177f68970728e9e6ba17fadbbb21fb470c6a1785d2ce42d0400238d7140639
- 预期效果：boot 后 free heap ≈ 136K（128K + 16K − 未量化杂项），
  高于 smoke 已验证可用的 128K 水位。

### 待 Ghee 决定

烧录请求 #3（见会话汇报）。不烧则 A/B/C 均无法执行（每一轮都依赖
LLM 心跳诊断）。

## 烧录 #3 后的复验（08:47–09:00，进行中）

- 编译证明：nsh_commands.c.*.o 时间戳 08:13:58（两次增量编译均为
  `CC: src/channels/nsh_commands.c`，第一次带 unused-function 警告，
  删除多余函数后 08:14 干净重编）。
- 实测内存（buggy_app bug & 先启 + ai_agent，新固件）：
  nsh free：total=381,168 used=90,432 free=290,736 **maxfree=288,752**
  agent 启动后：**free heap 136,664**（旧固件同场景 120,280；M3 同场景
  140,800）——恢复量 ≈ 16.4KB，与删除 rb.0 一致。
- fwpush 正例（boot 后立刻）：`fwpush: OK 6388 bytes, fnv1a=df9dc4f8
  -> /data/ai_agent/patches/buggy_app_fixed`（新校验逻辑首次通过）。
- fwpush 负例① 截断包：`fwpush: size mismatch got=3000 want=6388`
  （fresh-boot 重跑；注意：在长跑状态 free=11.6K 时首次尝试出现过
  `write failed (errno=12)`——tmpfs 写入与 LLM 轮峰值争堆，C 轮流程
  在 boot 后 20s 内 push，不受影响；此现象记入 0024 说明）。
- fwpush 负例② 坏校验和：进行中。
- TLS：新固件上已见 `Reusing pooled connection` + `OpenAI API with
  tools (… 9390 bytes, alloc_fail=0)`，待完整一轮 END status=ok 后开
  C r1（Ghee 要求 4）。
- fwpush 负例② 坏校验和（fresh-boot 重跑）：`fwpush: CHECKSUM MISMATCH
  rlen=6388 sum=df9dc4f8 want=df9dd6cc - payload deleted`，payload 已
  删除、无崩溃。**三个 fwpush 用例在新校验逻辑下全部通过**（正例 OK /
  截断拒绝 / 坏校验拒绝）。
  补充观察：第一次 NEG2 尝试与首轮心跳撞车时 tmpfs 写入报 errno=12
  （堆瞬时不足），C 轮流程在 boot 后 20s 内 push，不触碰该窗口；
  现象记入 0024 说明（Ghee 要求 6）。

## 09:21–09:47 完整心跳轮观察（m4-smoke3-full-round.log，watcher 捕获 2 轮）

两轮都 END status=fail，逐项分析：

**第 1 轮 (6aefcd4403cd357a)**：5 次 LLM 调用全部成功（最大请求 11,770 B，alloc_fail=0），TLS 握手成功 3 次。失败点：第 6 次调用（11,770 B）时 `Write request failed: -5`。定位：vela_tls.c tls_write_request() 开头 `malloc(4096)` 失败 → VELA_TLS_ERR_OVERFLOW(-5)。**这是堆碎片/耗尽下的瞬态分配失败，不是 TLS 握手问题**——握手本身 OK。该轮未到 recover（iter5 即失败）。

**第 2 轮 (6aefcdbc2746feb7)**：6 次 LLM 调用成功，recover_task 被调用（action=resume）。L1 无效后走 L2 restart → post_delta=-1（respawn 失败？需查）→ 判定 needs_human。日志有 `[recover] hotfix payload missing: /data/ai_agent/patches/buggy_app_fixed` —— **预期行为**：NEG2 坏校验测试把 payload 删了，板子从 09:07 起一直没重新推包。随后第 7 次调用 8300 B 时 `alloc_fail=1 +1`（序列化树分配失败）→ llm=fail。

**关键观察**：
1. **malloc(4096) 偶发失败**说明稳态空闲虽有小堆块但 4096 连续块偶发不可得。之前的测量 agent free heap 136,664，但 free 显示 low memory 13,952——这说明心跳轮进行到深迭代时（请求体 11.7 KB）瞬时占用高。
2. buggy_app 未启动（NEG1/NEG2 测试期间板子从未注入 buggy_app bug？不对——第 2 轮 recover 显示 pre_delta=0 即 buggy_app 已卡死。回看：09:07 启动序列注入了 `buggy_app bug &`。）
3. recover 的 L2 respawn 失败原因待查：run_shell ps 显示 buggy_app 存在但 post_delta=-1。

## 10:00–10:10 健康轮判定尝试（m4-smoke4-san.r1）

板子 09:07 启动后未复位持续运行约 65 分钟（期间跑过 NEG1/NEG2 和 2 轮失败心跳）。A 场景健康轮结果：END status=fail，cause=net_llm。失败点与 full-round 第 1 轮完全同型：iter-5 请求体 ~11.8 KB 时 `Write request failed: -5`（tls_write_request 的 malloc(4096) 失败），本轮 netpkt_alloc_fail=12。

**判定**：这与 M1 时代已知模式一致（m1-acceptance.md：碎片化时 netpkt 分配失败成簇，maxfree 见底）。板子连续运行 65 分钟 + 多轮失败请求后堆碎片化，不是 M4 代码回归的判据。**判别实验**：C r1 的流程本身会复位板子（fresh boot 干净堆），若 fresh boot 上 iter-5 malloc(4096) 仍失败，则记为 M4 内存问题并按规则停下汇报。

（附：用户要求 5 已记录——任何内存分配失败均记 M4 内存问题并单独标注。本轮 alloc_fail=0，无 X509 失败；malloc(4096) 失败 1 次发生在 -5 处，单独标注为 **M4 内存问题（待判别）**。）

**时间纪律**：现在 10:11，截止 11:30。C r1（约 15–18 min）→ A×10（约 80 min，将占满剩余时间）→ C 剩余 4 轮大概率放不进窗口。按用户指令顺序执行，11:30 汇报未完成轮次。

## 10:33 C r1 结果 + 10:35–10:53 M4 内存回归判定（Ghee 指示，c225）

### C r1（烧录 #3 固件，fresh boot 10:12:47，m4-C.r1 + m4-C.r1.push.log + m4-C.r1.setup）

- push：attempt 1 rc=0，`fwpush: OK 6388 bytes, fnv1a=df9dc4f8 -> /data/ai_agent/patches/buggy_app_fixed`。
- 观察窗 10:16:28 起：**8 次心跳轮全部 `END status=fail`**，每次都在 iter-0、
  请求体 8,809 B、TLS 握手成功后 `Write request failed: -5`。llm_ok=0。
- cause=net_llm（归类口径不变），但按 Ghee 要求 5，本轮实际失败是
  **内存分配失败（-5 = tls_write_request 内 malloc(4096) 失败）**，
  单独标注为 **M4 内存问题（功能失败）**，非网络失败。
- L3 未被执行到（每轮 iter-0 即死）。pass=false。

### M4 vs M3 同位置数据对照（Ghee 要求 1、4）

| 指标 | M3（11-04 证据） | M4（今日烧录 #3） | 出处 |
| --- | --- | --- | --- |
| agent 启动后 free heap（A 场景） | **141,000** | **136,664** | M3: m3-overnight/runner.log r1–r6 agent_start_free；M4: m4-smoke3-boot.log / m4-smoke4-san.r1 / m4-C.r1.setup（三处一致） |
| agent 启动后 free heap（C 场景，buggy_app bug 先启） | **140,800** | **136,664**（实测） | M3: 2026-11-04/m3-c2/runner-c2.log agent_start_free；M4: m4-C.r1.setup |
| nsh free 启动诊断后 maxfree | –（未采） | **288,752**（boot 后、LLM 轮前） | m4-smoke3-boot.log（08:47:39 free 输出） |
| 诊断轮中 maxfree | **11,448–15,552** | （未采到，见下） | M3: m3-acceptance.md 表（r1/r8）+ m3-overnight/runner.log |
| 请求体峰值成功上限 | **12.2–13.2 KB 成功**（req_peak 12428–13214） | **11.8 KB 必败**（11796/11800 两次实测均 -5） | M3: runner-c2.log req_peak；M4: m4-smoke4-san.r1（两轮同位置失败）、m4-smoke3-full-round.log |
| 恢复报告写入调用 -5 失败 | 罕见（50 轮中仅 r9、B-r9 两处） | 主导（C r1 全部 8 轮 iter-0 即 -5） | M3: m3-acceptance.md 注*、B 重跑注；M4: m4-C.r1 |

**实测 vs 预期分开写**：
- 实测（上表全部行）：M4 固件 agent 启动 free heap 136,664，
  比 M3 低 **4,136–4,336 B**；请求体 11.8 KB 处 -5 必败（2/2），
  payload 在位时 8.8 KB 也 -5（8/8）。
- 预期（smoke 前的估计，已被实测推翻）：删 16 KB rb.0 后
  "boot 后 free heap ≈ 136 K，高于 smoke 已验证可用的 128 K 水位"
  （m4-smoke-notes.md 修复节）。实测 136,664 确实≈136 K，
  但 **M3 的可用水位是 140.8–141 K**，不是 128 K——
  预期基准写错了，修复并未恢复到 M3 水平。

### 判定（按 Ghee 判别标准，要求 4）

**M4 内存回归：成立。** 依据：
1. 同为 fresh boot、无 payload：M3 在 maxfree 11.4–15.5 KB 时
   12.2–13.2 KB 请求成功；M4 在 agent 启动 free 136,664 时
   11.8 KB 请求 -5（m4-smoke4-san.r1 两轮同位置）。
2. M4 agent 启动 free heap 比 M3 低 4.1–4.3 KB（上表第 1、2 行），
   差值来自 M4 新增代码（exec_spawn 符号表 g_hotfix_exports、
   binfmt 模块句柄等驻留）——方向与"修复版比 M3 更吃内存"一致。
3. payload（6,388 B tmpfs 页）在位时进一步挤压：8,809 B 请求也 -5
   （m4-C.r1 8/8）。M3 无此场景对照，但 M4 在更小的请求上失败，
   按判别标准 4 不再用"碎片化"解释。
4. "长时运行碎片化"解释被排除：C r1 是 fresh boot（10:12:47 复位），
   第 1 次心跳轮（10:16）iter-0 即失败，无累积。

### 要求 4 的状态（如实记录）

**未满足**：截至今日测试停止，M4 固件上没有任何一轮完整成功的
心跳诊断（END status=ok 为 0）。C r1 不构成其替代。证据：
m4-smoke3-full-round.log（2 轮 fail）、m4-smoke4-san.r1（2 轮 fail）、
m4-C.r1（8 轮 fail）。

## A 轮（10:54 启动，11:09 按指示停止）— m4-A.r1 / m4-A.r2

**Ghee 补充规则**（11:00 前后）：出现第一次内存分配失败即停 A 轮；
误处置统计只计 END status=ok 的完整轮次，请求阶段失败的轮次单独列。

- **m4-A.r1**：fresh boot，agent_start_free=136,664。iter-5 请求
  11,690 B 时 `Write request failed: -5`（malloc(4096) 失败）→
  **第一次内存分配失败，按规则立即停止 A 轮**（11:09 停 runner）。
  该轮 END status=fail → **请求阶段失败，单独列出，不计误处置分母**。
- **m4-A.r2**：停止时正在第 2 轮 iter-5（11,531 B 请求在途、netpkt
  失败 2 次），日志无 END → 不完整轮，不计入任何统计，仅存档。
- 结果：A 场景完成 0 个 END status=ok 轮次。误处置统计：**无有效样本（0 轮完整），答辩后补测**。

至此今日板上测试全部结束（11:14，早于 11:15 硬停）。

## 11:33 刷回答辩版固件（Ghee 已独立核对 sha256 后确认）

- flash.sh 显式指定 /home/w/siliconloop-defense-1105.bin
  （906,600 B，sha256 3e315a36…df36e8c），地址 0x2000，
  esptool 校验 `Hash of data verified`，RTS 硬复位完成。
- 复检计划：1 轮健康（场景 A）+ 1 轮卡死（场景 B），日志
  m4-flashback-A.r1 / m4-flashback-B.r1；完成后 12:00 前释放串口。

### 健康复检通过（m4-flashback-A.r1，11:41–11:53）

- `{"status":"ok", iters=7, recover_called=false, oom=0,
  cause=ok, agent_start_free=139776, req_peak=12450, pass=true}`
- **END status=ok、无处置调用、请求峰值 12,450 B 成功**——答辩版
  固件功能完整，同时反证 M4 的 11.8 KB 必败确是 M4 固件自身回归
  （同板、同网、同 LLM 服务，M3/答辩版 12.45 KB 通过）。
- 误处置统计：本轮 1 个完整轮次，无处置调用 → 无误处置。

### 卡死复检通过（m4-flashback-B.r1，11:53–12:03）

- `{"status":"ok", iters=6, recover_called=true, recovered=true,
  cause=ok, agent_start_free=139776, req_peak=12347, pass=true}`
- 恢复判据：`{"level":1,"action":"resume","target":"buggy_app",
  "pre_delta":0,"post_delta":50,"result":"recovered"}` —— L1 软恢复
  即唤醒，Δ 0→50。
- 第一轮会话 END status=fail（B 场景首轮卡死复核窗）后恢复，第二轮
  END status=ok；scenario.py B 判据 recover_called+recovered 通过。
- **误处置：无**（卡死判定正确，恢复针对 buggy_app 白名单目标）。

### 12:04 刷回复检完成，释放串口

两轮复检均通过，串口已释放，此后不再操作板子（Ghee 12:00 纪律，
实际 12:04 完成，超时 4 分钟，因 B 轮窗口较长）。
