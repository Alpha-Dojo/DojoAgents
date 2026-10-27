# 异步运行时设计（AnyIO 边界）

本页是 DojoAgents 异步运行时的权威设计：哪些模块可以使用 `asyncio`、异步任务由谁拥有、
超时与取消如何表达、线程与内存如何限界。所有新增生产业务代码必须遵循本页。

迁移前的 `asyncio` 使用已按阶段收敛，引用矩阵由 `.agents/scripts/audit_asyncio_usage.py`
生成，AST 门禁由 `tests/test_asyncio_boundaries.py` 强制。

## 1. AnyIO 架构边界

三层结构，依赖方向单向向下：

| 层 | 模块 | 职责 |
| --- | --- | --- |
| 业务层 | `dojoagents/{agent,gateway,dashboard,tools,multi_agent,planning,memory,...}` | 只使用 AnyIO 原语，**禁止** `import asyncio` |
| 原语层 | `dojoagents/utils/async_runtime.py` | 有界同步卸载、保序并发、超时包装、取消判定 |
| 桥接层 | `dojoagents/utils/blocking_portal.py` | 同步线程 ↔ 事件循环的唯一受支持通道 |

原语层对外只暴露四类能力：

- `run_sync_bounded(function, /, *args, workload=..., limiter=..., abandon_on_cancel=False, **kwargs)`
  —— 把阻塞调用卸载到有界线程池，kwargs 用 `functools.partial` 绑定（AnyIO 的 `run_sync` 只转发位置参数）。
- `gather_ordered(operations, *, max_concurrency=None, return_exceptions=False)`
  —— 并发执行并**保持输入顺序**；子任务异常留在自己的槽位，兄弟继续跑完，最后按输入序抛首个异常，
  **不向调用方泄漏 `ExceptionGroup`**。
- `operation_timeout(timeout_seconds, *, operation=...)`
  —— 只把**本 scope 自己触发的**超时转换为 `OperationTimeoutError`；被调用代码自己抛的 `TimeoutError` 原样透传。
- `is_cancelled_exception(exc)` —— 等价于 `isinstance(exc, anyio.get_cancelled_exc_class())`，必须在异步上下文调用。

工作负载档位与容量（`dojoagents/utils/async_runtime.py`）：

| 档位 | 容量 | 用途 |
| --- | --- | --- |
| `SyncWorkload.FILE_IO` | `FILE_IO_LIMIT = 16` | 本地文件、JSON/JSONL 读写 |
| `SyncWorkload.SDK_IO` | `SDK_IO_LIMIT = 8` | DojoSDK 与外部数据源调用 |
| `SyncWorkload.CPU` | `CPU_WORK_LIMIT = 4` | 纯计算（pandas/polars 组装、指标计算） |

容量存放于 AnyIO `RunVar`（按异步上下文隔离），**不是在 import 时构造的模块级限流器**，
因此测试之间互不污染、后端无关。

## 2. TaskGroup 所有权

**每个后台任务必须有一个生命周期包住它的 TaskGroup owner。** 不允许自由漂浮的任务。

| 宿主 | owner | 位置 |
| --- | --- | --- |
| Dashboard 应用 | `service_tasks`（lifespan 内的 task group） | `dashboard/server.py` |
| Dashboard 单次 chat SSE | lifespan 的 `service_tasks` + 每请求 `OwnedSSEProducer` cancel scope | `dashboard/server.py` / `dashboard/sse.py` |
| 持久化 run 事件回放流 | lifespan 的 `service_tasks` + 每请求 `OwnedSSEProducer` cancel scope | `dashboard/server.py` / `dashboard/sse.py` |
| Dashboard 后台 agent run | `AgentRunManager` 持有的 portal 循环 | `dashboard/agent_runs.py` |
| Agent 事件扇出 | `AgentEventBus` 的 `dojo-events:<run_id>` 任务 | `agent/session_run.py` |
| Agent 心跳 | `dojo-heartbeat:<run_id>` | `agent/session_run.py` |
| Provider 流式对话 | `dojo-provider-chat` | `agent/loop.py` |
| Gateway 服务 | `gateway/server.py` 的 task group | `gateway/server.py` |
| Gateway runner 长驻任务 | `GatewayRunner._owned_task_group` | `gateway/runner.py` |
| Gateway 流消费 | `stream_consumer._run_owned` | `gateway/stream_consumer.py` |
| MCP server 监督循环 | `server_tasks`（每次会话周期一个） | `tools/mcp_tool.py` |
| 多 Agent 团队 | `AgentTeam._task_group` | `multi_agent/team.py` |
| 子进程 drain/reap | `dojoagents/utils/detached_tasks.py`（唯一例外，见 §9） | `tools/process_registry.py` |

规则：

- **禁止裸 `asyncio.create_task()`。** `create_task` 只能出现在 `detached_tasks.py` 内部。
- TaskGroup 的 `__aenter__`/`__aexit__` 必须在**同一任务、同一深度**完成。跨任务打开一个
  task group 再在别处退出，会抛
  `RuntimeError: Attempted to exit a cancel scope that isn't the current tasks's current cancel scope`。
  长驻组件（如 `GatewayRunner`）用「宿主任务长期存活」的方式持有它，短命任务里**不能**照抄。
- 一个组件需要「任务比创建它的请求活得更久」时，正确做法是让**组件**拥有一个专用的 portal
  事件循环（§3），而不是让任务脱离结构化并发。

## 3. 服务启动和关闭

### 3.1 跨线程桥：`ThreadedBlockingPortal`

`dojoagents/utils/blocking_portal.py` 把 `anyio.from_thread.start_blocking_portal` 包装成
显式、幂等的生命周期对象，供同步线程（CLI、信号处理器、插件注册）驱动异步组件：

```
start() → ready → 接受同步线程调用 → shutdown() 停止接受 → 关闭 portal → 线程退出
```

- `start()` 与 `shutdown()` 都幂等；重复调用不会产生第二个事件循环线程。
- `shutdown()` **先把状态切到 `closing` 并清空 portal 引用**，再触碰事件循环。
  因此关闭期间的迟到调用一律得到 `PortalClosedError`（可解释错误），而不是挂起。
- `portal.call(portal.stop, cancel_remaining=True)` 已让 `start_blocking_portal` 自己完成
  `thread.join()`，实现里**不得**再手写 join。
- 调用约束：`call()` / `start_task()` / `call_async()` 都拒绝从 portal **自己的事件循环线程**
  调用（`PortalThreadError`），否则必然自锁。
- `call_async()` 会占用一个 worker 线程（AnyIO 没有「无线程等待外部循环」的原语），
  因此走 portal 私有 `CapacityLimiter(bridge_concurrency=8)`，避免挤占项目的文件/SDK 线程池。
- `run_sync()` 是跨循环 Future 取消、等待收敛和同步关闭的唯一异步入口；它复用同一个
  portal 私有 limiter，并在内部调用 `run_sync_bounded()`，业务模块不得直接调用
  `anyio.to_thread.run_sync()`。
- 超时语义：`call()` 超时抛 `PortalCallTimeout`。取消是在**后台守护线程**里发起的 ——
  `concurrent.futures.Future.cancel()` 会内联执行 done callback，而 portal 的 callback 必须把
  取消交回 portal 循环，在超时的调用者线程上直接调用会**二次阻塞**。
- 同理，**从事件循环线程**调用 `future.cancel()` 会死在 `call_soon_threadsafe`；
  故取消与等待一律走 `await portal.run_sync(future.cancel, abandon_on_cancel=True)`。
- 无 `__del__`，不依赖 GC 做异步清理。

默认超时：`DEFAULT_CALL_TIMEOUT_SECONDS = 120`、`DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 10`。

### 3.2 组件启动 / 关闭顺序

| 组件 | 启动 | 关闭 |
| --- | --- | --- |
| Dashboard | `lifespan` 建 `service_tasks`，`DashboardAppServices.startup(task_group=...)` | `service_tasks.cancel_scope.cancel()` → 屏蔽取消的收尾序列 |
| Dashboard 金融数据服务 | `app_container.startup()` 在 `async with anyio.from_thread.BlockingPortal()` 内运行 | `app_container.shutdown()` |
| Dashboard 后台 run | `AgentRunManager.__init__` 建并启动自己的 portal | `AgentRunManager.shutdown()`：先取消所有 run 并等 `settled`，再 `portal.shutdown()` |
| MCP | `MCPToolRuntime.start_server()`：启动 portal → 启动 `serve()` 监督任务 → 轮询 `ready` | `MCPToolRuntime.shutdown()`：停所有 server → 清空 → `portal.shutdown()` |
| Gateway | `gateway/server.py` 的 task group | 同上，group 退出即收敛 |

**关闭序列必须整体包在 `with anyio.CancelScope(shield=True):` 内**（见 `dashboard/server.py`）。
原因是：`service_tasks.cancel_scope.cancel()` 会让**当前任务本身**进入取消待处理状态，
此后 shield 之外的任何 await 检查点（含 `anyio.sleep(0)` 和
`to_thread.run_sync(..., abandon_on_cancel=True)`）都会立刻抛 `CancelledError`，
收尾根本跑不完。收尾是有界的尽力而为序列，必须跑到底。

**反向硬规则**：任何**关闭 cancel scope** 的 `__exit__`/`__aexit__` **不能**被
`CancelScope(shield=True)` 或 `move_on_after` 包住，否则抛
`RuntimeError: Attempted to exit a cancel scope that isn't the current tasks's current cancel scope`。
只有**含 awaited 检查点的 task-group `__aexit__`** 才违反此规则 —— 因此关闭的有界性由
「关闭函数自己的超时参数」提供（`shutdown(timeout=...)` / `MCP_*_TIMEOUT_SECONDS`），
不靠 scope 包装。

### 3.3 取消期间允许的操作

任务进入取消待处理状态后，只有 **shield 内**的 await 才能执行。需要落盘或告警的清理必须写成：

```python
finally:
    with anyio.CancelScope(shield=True):
        LOGGER.warning("run cancelled; persisting final state")
        await anyio.to_thread.run_sync(write_final_state)
```

未加 shield 的 `await` 会在第一个检查点抛 `CancelledError`，其后的同步语句不会执行。

## 4. 超时和取消规范

### 4.1 超时

- 硬截止（超时即失败）用 `anyio.fail_after(seconds)`，它把 `CancelledError` 转换为
  `TimeoutError`。**取消被限制在该 scope 内，不泄漏给调用者。**
- 「超时后继续走正常路径」用 `anyio.move_on_after(seconds)` 并检查 `scope.cancelled_caught`，
  例如「轮询到点就 flush 一次」。
- 需要把超时区分成「自己的超时」与「内层已有的 `TimeoutError`」时，用
  `async_runtime.operation_timeout()`。
- 所有超时值必须是**具名常量或配置项**，不允许散落的字面量。现有约定：

| 组件 | 常量 | 默认值 |
| --- | --- | --- |
| 工具执行 | `sandbox.timeout_seconds` | 来自 SandboxPolicy |
| Portal 调用 / 关闭 | `DEFAULT_CALL_TIMEOUT_SECONDS` / `DEFAULT_SHUTDOWN_TIMEOUT_SECONDS` | 120 / 10 |
| MCP 连接 / 启动 / 停止 / 调用 / 关闭 | `MCP_CONNECT_` / `MCP_START_` / `MCP_STOP_` / `MCP_CALL_` / `MCP_SHUTDOWN_TIMEOUT_SECONDS` | 15 / 30 / 10 / 120 / 30 |
| MCP keepalive | `MCP_KEEPALIVE_INTERVAL_SECONDS` / `MCP_KEEPALIVE_TIMEOUT_SECONDS` | 180 / 30 |
| MCP 重连退避 | `MCP_RECONNECT_BACKOFF_SECONDS` / `MCP_RECONNECT_MAX_BACKOFF_SECONDS` | 1.0 / 30.0 |
| 子进程终止宽限 | `DEFAULT_TERMINATE_GRACE_SECONDS` | 5.0 |
| 子进程单行上限 | `DEFAULT_MAX_LINE_BYTES` | 4 MiB |
| 取消后等待 run 收敛 | `_RUN_CANCEL_SETTLE_SECONDS` | 10.0 |

MCP 的重连必须**先退避再重连**且退避有上限（`min(1.0 * 2 ** (n-1), 30.0)`），
否则会形成无节流的热重连。

### 4.2 取消

- 判定取消类型一律用 `anyio.get_cancelled_exc_class()`，**不要**写 `asyncio.CancelledError`
  （它在 asyncio 后端不是 `Exception` 的子类，`except Exception` 已经抓不到它 —— 这正是我们要的行为）。
- **禁止用 `except Exception` 吞掉取消。** 捕获 `Exception` 的清理分支必须重新抛出取消，
  或者在边界处用 `BaseExceptionGroup.split()` 把取消挑出来单独抛：

```python
except BaseExceptionGroup as exc:
    cancelled, remainder = exc.split(anyio.get_cancelled_exc_class())
    if cancelled is not None:
        raise cancelled
    # remainder 才是业务错误
```

- **公共 API 不泄漏 `ExceptionGroup`。** 工具与路由边界把组拆开、把取消抛出、把业务错误
  转成 `ToolResult(ok=False, error=...)` 或 HTTP 错误。`gather_ordered` 已经保证这一点。
- 重复取消必须是幂等的：`CancelScope.cancel()` 可重复调用；也不允许对已退出作用域的
  `Future` / 任务重复取消。取消要收敛到「等待 `settled`，超时再兜底置状态」，见
  `AgentRunManager.cancel_run()`。
- 取消期间仍要完成日志与持久化 → 见 §3.3 的 shield 写法。

## 5. Thread limiter

- 所有阻塞 I/O 必须经 `run_sync_bounded(...)` 走有界线程池，**不允许**裸
  `anyio.to_thread.run_sync()` 或自建 `ThreadPoolExecutor`。
  裸调用会落到 AnyIO 默认 40 线程上限，且与其它子系统共享，无法按负载隔离。
- 选择正确的 `workload` 档位，不要把所有阻塞工作都塞进 `FILE_IO`。
- `abandon_on_cancel` 默认 `False`：写入类操作必须等 worker 结束，不能中途放弃。
  只有「结果可丢弃」的读操作才允许 `abandon_on_cancel=True`。
- 需要独立限流时可以显式传 `limiter=`（例如 portal 的自有桥接限流器），但必须是有界对象。
- Portal 生命周期桥接统一调用 `ThreadedBlockingPortal.run_sync()`；该方法使用 portal 私有的
  有界 limiter，避免与文件 I/O、SDK I/O 共享容量。
- 验收观测：提交 `2 × FILE_IO_LIMIT` 个阻塞任务，实测并发峰值必须等于 `FILE_IO_LIMIT`。
  参见 `tests/test_resource_bounds.py`。

## 6. Memory stream 容量规范

`anyio.create_memory_object_stream()` **必须显式传入有限的 `max_buffer_size`**。
禁止 `math.inf` / `float("inf")` / 省略参数 —— 门禁测试
`test_memory_object_streams_have_explicit_finite_buffers` 会失败。

现状登记（改动必须同步本表）：

| 位置 | 容量 | 消费者 |
| --- | --- | --- |
| `agent/loop.py` | 64 | provider delta → agent 事件 |
| `agent/session_run.py` | 32 | 事件扇出到 session 日志 |
| `gateway/stream_consumer.py` | 64 | 编辑器流式刷写 |
| `dashboard/sse.py`（`SSE_EVENT_BUFFER_SIZE`） | 32 | SSE 事件推送 |
| `dashboard/server.py`（chat SSE） | 32 | SSE 事件推送 |
| `dashboard/server.py`（持久化 run 回放） | 1 | 事件重放 |
| `tools/process_registry.py` | 32 | 后台进程完成通知 |

背压约定：

- 发送端在循环内用 `send_nowait()`。缓冲满时必须在**有界时间**内失败，而不是无限等待；
  `dashboard/sse.py` 抛 `StreamBackpressureError`，其它位置抛带 `(capacity=N)` 文案的
  `RuntimeError`。容量文案必须与真实 `max_buffer_size` 一致。
- 发送端关闭即终止信号。消费者依赖 `anyio.EndOfStream` / `ClosedResourceError`；
  `receive()` 在 EOF **抛异常**而不是返回空值。
- 需要跨线程投递时见 §7，不要给 stream 加无限容量。

## 7. SSE 跨线程桥接

SSE 事件由 agent 回调产生，回调可能运行在 worker 线程上，而 memory stream 绑定在事件循环上，
因此必须经由 `BlockingPortal` 投递。

- `dashboard/sse.py::SSEEventStream` 持有 `send_stream` / `receive_stream`（容量 32）与一个
  可选 `_portal`。
- `bind_portal(portal)` / `unbind_portal()` 由 app-owned producer 在 `async with` 内成对调用：
  同线程回调走 `send_nowait()`，外部线程回调走 `portal.call(send)`。**迟到或已关闭的回调静默丢弃。**
- portal 在**事件循环内**创建（`async with anyio.from_thread.BlockingPortal() as portal:`），
  不新建线程、不新建循环，作用域限于该 producer，`finally` 中 `unbind_portal()`。
  这与「每个请求手搓一个事件循环线程」不是一回事，但它是「不要每请求创建 portal」这条规则的
  字面例外，登记在此以免被误判为违规。
- 生产者由 lifespan 的 `service_tasks` 拥有；`OwnedSSEProducer` 在 producer 任务中进入并退出
  每请求 cancel scope。响应 generator 只 drain receive stream，不跨 `yield` 持有 TaskGroup、
  BlockingPortal 或 CancelScope。客户端断开时 generator 调用 `producer.stop()`，有界等待清理完成。
- 发送端关闭走 `with anyio.CancelScope(shield=True): await event_stream.close()`；持久化回放的
  async iterator 也由 producer 在同一任务中关闭。
- Gateway 侧同样模式：`gateway/stream_consumer.py` 在循环内创建 portal、由
  `task_group.start_soon(self._run_owned)` 拥有生产者。

## 8. Subprocess 回收

统一的进程适配层在 `dojoagents/tools/processes.py`（`Process`、`open_process()`、
`run_process()`、`ProcessResult`、`terminate_then_kill()`，并再导出
`PIPE` / `DEVNULL` / `STDOUT` / `INHERIT`）。业务代码**不得**直接使用
`asyncio.create_subprocess_*` 或 `anyio.open_process()`。

- `anyio.open_process()`（本适配层的 `open_process()`）返回的进程是**游离**的：
  作用域退出或被取消**不会**杀掉子进程，必须显式回收。
- `run_process()` 用于短命令；调用方被取消时 AnyIO 会回收子进程。
- 回收一律用 `terminate_then_kill(process, *, grace_seconds=5.0)`：
  `SIGTERM → 宽限 → SIGKILL → wait()`，整段包在 `anyio.CancelScope(shield=True)` 内，
  因此可以从 `finally`、超时处理器或取消处理器里安全调用，且保证子进程被 reap，不留孤儿。
  已退出的进程上调用是幂等的。
- 长驻子进程的 stdout 排空与收割必须活得比启动它的工具调用更久 →
  使用 `dojoagents/utils/detached_tasks.py`（§9 的唯一例外），并配合
  `process_registry` 的动态剪枝与 reaper 直接持有 session 对象。
- 长驻进程的 `stdin/stdout/stderr` 用 `INHERIT`（= `None`，即继承），让日志可见；
  改成 `PIPE` 会让日志消失并可能写满管道把子进程卡死。
- `Process.communicate()` 是本层自实现的（AnyIO 字节流没有 `communicate()`）。
- `DEFAULT_MAX_LINE_BYTES = 4 MiB` 限制单行读取，防止无换行输出撑爆内存。

## 9. asyncio 兼容白名单

生产代码只允许两个文件 `import asyncio`，二者都登记在
`tests/test_asyncio_boundaries.py::PERMANENT_ASYNCIO_ALLOWLIST` 与
`.agents/scripts/audit_asyncio_usage.py::PRESERVE_ALLOWLIST`：

| 文件 | 原因 | 移除条件 |
| --- | --- | --- |
| `dojoagents/tools/af_unix_asyncio_compat.py` | AnyIO 不提供 AF_UNIX 高层 helper；该模块同时补 Windows Proactor 下的 AF_UNIX 支持 | AnyIO 提供等价的 AF_UNIX 连接/服务端原语后整体删除 |
| `dojoagents/utils/detached_tasks.py` | AnyIO 是结构化并发库，**没有** fire-and-forget 原语，而后台进程的 drain/reap 必须活得比创建它的调用更久 | AnyIO 提供公开的、scope 安全的 detached task 原语后整体删除 |

`TEMPORARY_ASYNCIO_ALLOWLIST` 为空集合，且必须保持为空 —— 它是迁移棘轮：
任何新增 `asyncio` import 都会让 `test_asyncio_imports_are_confined_to_registered_boundaries` 失败。

除上述白名单外，新增生产业务代码必须使用 AnyIO，**不得**新增 `asyncio` import、
裸后台任务或无界异步队列。测试文件暂不纳入生产零引用要求。

保留条件（新增白名单条目必须逐条满足）：

1. 第三方库明确要求 asyncio，或 AnyIO 确认无等价原语（需附探针证据）；
2. 已压缩为极薄 adapter；
3. adapter 内不含业务逻辑；
4. asyncio 类型不泄漏到公共接口；
5. 文件顶部说明原因与移除条件；
6. 已登记在 AST 白名单测试中。

已知偏离：`detached_tasks.py` 不满足条件 1 的「第三方库」表述（属 AnyIO 原语缺口，
已在文件顶部附三条探针证据），且 `start_detached()` 曾返回 `asyncio.Task`（条件 4），
现已改为不暴露 asyncio 类型。

## 10. 新服务模板

新增需要后台任务或同步桥的服务时，照此骨架：

```python
from __future__ import annotations

import anyio
from dojoagents.logging import LOGGER
from dojoagents.utils.async_runtime import SyncWorkload, run_sync_bounded

# 1) 所有超时/容量都是具名常量
START_TIMEOUT_SECONDS = 30.0
STOP_TIMEOUT_SECONDS = 10.0
EVENT_BUFFER_SIZE = 32


class MyService:
    """后台服务：由 TaskGroup 拥有任务，由显式方法关闭。"""

    def __init__(self) -> None:
        self._started = False
        self._closed = False
        self._owns_group = False

    async def startup(self, *, task_group: anyio.abc.TaskGroup | None = None) -> None:
        if self._started:
            return                                   # 幂等
        self._started = True
        with anyio.fail_after(START_TIMEOUT_SECONDS):
            await self._connect()
        # 2) 后台任务必须有 owner。
        #    优先借用调用方的 task group（FastAPI lifespan 就是这么传的，
        #    该 group 的 __aenter__/__aexit__ 都由 lifespan 那个长期存活的任务完成）。
        if task_group is None:
            # 只有在本服务的 startup/shutdown 会由**同一个长期存活的任务**调用时，
            # 才能自建 group 并在这里 __aenter__：cancel scope 绑定当前任务，
            # 跨任务退出会抛
            # RuntimeError: Attempted to exit a cancel scope that isn't the current
            # tasks's current cancel scope。
            raise RuntimeError(
                "MyService needs a host task group; pass the owner's group or give "
                "this service a dedicated long-lived task / ThreadedBlockingPortal"
            )
        self._owns_group = False
        task_group.start_soon(self._run, name="dojo-my-service")

    async def _run(self) -> None:
        while True:
            await anyio.sleep(0)                     # 结构化循环，随 owner 一起取消

    async def shutdown(self, *, timeout: float = STOP_TIMEOUT_SECONDS) -> None:
        if self._closed:
            return                                   # 幂等
        self._closed = True
        # 3) 收尾必须有界：用关闭函数自己的 timeout，不要用 scope 包住别人的 __aexit__
        with anyio.move_on_after(timeout):
            await self._close_quietly()

    async def _close_quietly(self) -> None:
        try:
            with anyio.CancelScope(shield=True):     # 4) 清理期间不被取消打断
                await self._disconnect()
        except Exception:                            # noqa: BLE001 - 清理必须尽力而为
            LOGGER.exception("MyService cleanup failed")

    async def _blocking_read(self, path: str) -> bytes:
        # 5) 阻塞 I/O 走有界 limiter
        def _read() -> bytes:
            with open(path, "rb") as handle:
                return handle.read()

        return await run_sync_bounded(_read, workload=SyncWorkload.FILE_IO)
```

模板要点：幂等 `startup`/`shutdown`；超时具名；后台任务有 owner 且**优先借用宿主 task group**；
清理加 shield；阻塞 I/O 经 `run_sync_bounded`；跨线程投递用 `ThreadedBlockingPortal`；
取消用 `anyio.get_cancelled_exc_class()` 判定；公共方法不返回 `ExceptionGroup`。
