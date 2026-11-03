# tools/host-test — 主机端内存守卫测试框架

从固件源码的 `[TESTABLE]` 标记区**逐字提取**真实代码，在主机上跑
探针有效性与所有权安全测试。M2/M3 继续复用此框架。

运行：`bash tools/host-test/run.sh`（gcc + cJSON 源码 + ASan/UBSan）

## 测试项与结果（2026-11-03）

### 1. alloc_probe_test — 探针有效性（Ghee 验证项 1）

对 `build_openai_tools_array` + 请求树组装阶段逐个注入 malloc 失败
（fail_at=1..120），断言：

- **A. 计数有效**：120/120 注入失败全部被 `alloc_fail` 计数捕获；
- **B. 校验器能抓住丢字段**：120/120 不完整树被 `validate_request_tree`
  拒绝（tools 丢 name / tools 整体丢失 / messages 缺失都会被拒）；
- **C. 零误判**：校验器与独立检查器无任何矛盾（lies=0）。

**结论：探针有效。** 固件里"50 轮 alloc_fail=0"的数据作数；
若校验器拦下请求（"request tree incomplete"），同日志必带 alloc_fail 计数。

单份 cJSON 核对：`nm nuttx | grep cJSON_PrintUnformatted` = 1 处，
`nuttx.map` 显示唯一来源 `libapps.a(cJSON.c…netutils.cjson…o)`（bailian_sdk
的 cJSON 未链接）；`cJSON_InitHooks/global_hooks` 在符号表中，钩子覆盖
全部 malloc/free 路径。**已知边界**：该 cJSON 版本的 Hooks 不含 realloc_fn，
realloc 失败不计数——但 realloc 只用于堆回退打印，其失败走
"OOM: failed to serialize" 独立日志，不沉默。

### 2. asround_test — 所有权安全（Ghee 验证项 2，ASan+UBSan+泄漏检测）

用录制的真实消息形状（reasoning 含 CJK、tool_calls、tool 结果）跑
20 轮，轮换固件的五条出口路径：正常发送 / 400 落盘 / 超时释放 /
超大 body 堆回退打印 / 树不完整拒绝。

**结果：ASan、UBSan、泄漏检测全部零报告。**

### 出口路径审计（llm_chat / llm_chat_tools，先 detach 再 delete）

| 路径 | 借用树归还 | 释放配对 | 结论 |
| --- | --- | --- | --- |
| 组装后正常发送 | detach messages + sys + tools_cache 后才 Delete(body) | req_release 恰好一次 | ✅ |
| 校验失败（tree_ok!=OK） | 同上（teardown 在校验判断之前完成） | 无请求缓冲 | ✅ |
| 序列化失败（post_data NULL） | 同上 | req_release(NULL) 解锁 | ✅ |
| llm_http_call 出错 | 不涉及借用树 | req_release 后 return | ✅ |
| 重试循环（429） | 不涉及 | 缓冲跨重试复用，锁持有 | ✅ |
| 400 落盘 | 不涉及 | **已修**：原在 req_release 之后读 post_data（悬垂读），改为落盘后再 release | ✅ |
| llm_chat 同型路径 | 无借用树（自解析 messages_json） | 配对完整 | ✅ |

工具数组缓存（s_tools_cache/s_tools_key）：请求间复用、body 删除前
detach；换 tools_json 时先 Delete 旧缓存再重建；进程内单线程访问
（agent loop 任务），无并发窗口。

### 3. recover_guard_test — 守卫与升级逻辑（Ghee 验证项，ASan+UBSan）

编译**真实的 tool_recover.c**（stub 平台头 + 真实头文件）：

| 场景 | 断言 | 结果 |
| --- | --- | --- |
| A 健康态 20 次调用 | 全部 refused（板上验收同款） | 20/20 ✅ |
| B stall → L1 SIGUSR1 | recovered，复现观察通过 | ✅ |
| C L1 无效 → L2 失败 | needs_human（升级给人） | ✅ |
| D 恢复后观察窗内复发 | recurred → needs_human | ✅ |
| E PID 文件过期号码被复用 | refused:pid_mismatch（绝不误伤他进程） | ✅ |
| F 处置进行中再次调用 | refused:busy | ✅ |
| G action=reset/test 走工具入口 | refused:cli_only（人工 CLI 专属） | ✅ |

零 ASan/UBSan/泄漏报告。worker 进程用 prctl 改名为 buggy_app 以
通过 PID 身份核对。
