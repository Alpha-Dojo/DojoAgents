# SessionStore / BlobStore 外部适配器规范

DojoAgents Core 不依赖 MySQL、PostgreSQL 或对象存储驱动。在线项目通过 `sessions.store.factory` 与 `sessions.blob_store.factory` 注入适配器；工厂使用 `module:attribute`，接收一份隔离复制的 options，并返回满足 `SessionStore` 或 `BlobStore` Protocol 的对象。

## 生命周期与错误边界

- `startup()`、`health()`、`shutdown()` 必须异步、可重复调用；启动失败应释放已创建的连接池。
- `health()` 只执行有界轻量查询，返回 `StoreHealth`，不得泄漏 DSN、密码、token 或 endpoint credential。
- 每个写操作使用短事务；不得跨 LLM、网络工具调用或 SSE 连接持有数据库事务。
- “不存在”和“无权访问”统一映射为 `SessionNotFoundError`，防止通过 ID 探测其他用户资源。
- 乐观版本冲突、租约冲突和 fencing token 失败映射为 `SessionConflictError`。

## SQL 数据与索引语义

所有 session、message、turn、run、event、usage、checkpoint、object、lease 查询必须带 `(tenant_id, user_id)` scope；只按公开 `session_id`、`run_id` 或 `object_id` 查询是不合格实现。

至少需要下列唯一性约束（具体表名可由项目决定）：

- session: `(tenant_id, user_id, session_id)`；内部 `session_uid` 全局唯一。
- run: `(session_uid, idempotency_key)` 和 owner scope 下的 `run_id`。
- event: `(run_uid, sequence)`；非空 idempotency key 也应唯一。
- message: `(session_uid, agent_id, sequence)`；turn: `(session_uid, sequence)`。
- usage: `(run_uid, idempotency_key)`；checkpoint: `(session_uid, namespace, key)`。
- object/blob linking 必须保存 owner scope、状态和版本，pending/committed/deleted 转换应可重试。

租约获取、续约、释放和 takeover 必须使用条件更新，同时校验 version、lease id、holder、expiry 与 fencing token。旧 worker 的 fencing token 永远不能提交新事件或 turn。

Session 心跳在所属 Run 的 AnyIO TaskGroup 中独立运行。每轮按 `sessions.runtime.heartbeat_seconds` 实际续租，不再等到租期消耗一半；正常轮次的间隔包含 RPC 耗时。完整心跳（续租 + Run 状态读取）的超时取 10 秒、半个心跳间隔与当前剩余租期中的最小值。临时失败短暂退避，最多连续失败三次，每次重试重新读取最新 lease 的剩余时间；租期耗尽后不再请求续租。

事件写入器或心跳确认丢租时立即取消所属运行；事件入队与终态准备保留原始 `SessionLeaseLostError`，不以已关闭队列的 `BrokenResourceError` 覆盖它，也不再尝试取消/完成等终态写入。外部主动取消仍走原取消流程。

Schema 变更使用显式、可审计、可回滚的迁移版本；应用进程不得在正常请求中隐式修改生产 schema。生产连接必须启用 TLS、最小权限账号、连接/查询超时和容量受限的连接池。

## 外部 conformance gate

适配器项目安装自己的驱动后设置：

```bash
export DOJO_TEST_SESSION_STORE_FACTORY='project.adapters.mysql:create_session_store'
export DOJO_TEST_SESSION_STORE_OPTIONS='{"dsn_env":"TEST_MYSQL_DSN","namespace":"ci-run-123"}'
export DOJO_TEST_BLOB_STORE_FACTORY='project.adapters.s3:create_blob_store'
export DOJO_TEST_BLOB_STORE_OPTIONS='{"bucket":"disposable-ci","prefix":"ci-run-123"}'
uv run --extra dev python -m pytest tests/sessions/test_external_store_contract.py -q
```

环境变量存在时不允许跳过任何 contract 能力。CI 使用一次性 schema/bucket prefix；工厂自行从 secret manager 或命名环境变量读取凭据，options 和测试输出不得包含明文 secret。

## File → SQL / Object Storage 切换演练

在一次性环境按以下顺序验收，并把适配器版本与命令输出保存到部署验收记录，而非仓库：

1. 对 file store 导出执行 dry-run，记录 session/message/turn/run/event/object 数量与 blob SHA-256。
2. 首次导入；再执行第二次导入，确认 idempotency key 和唯一索引使数量不增长。
3. 比较逐 scope 数量、事件 sequence、checkpoint version、对象大小和 blob checksum。
4. 用另一个 user/tenant 请求相同 session/run/object ID，所有读取均返回 not found。
5. 从 SQL 后端再次导出，与源导出的规范化 JSON 比较。
6. 模拟 worker 租约过期和 takeover，确认新 fencing token 增长，旧 worker 写入被拒绝。
7. 模拟 blob put 后 DB commit 失败、DB reserve 后 blob put 失败，确认补偿清理 pending 数据。
8. 切换读流量前完成备份与回滚演练；切换后监控冲突率、连接池、延迟和 orphan blob。

Core 的 file tests 始终不需要 SQL 驱动；只有目标在线项目的部署 gate 才安装并验证其适配器。
