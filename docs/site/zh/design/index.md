# 设计

本分类保存当前有效的技术设计和集成契约，用于说明某个子系统必须如何工作。

- [K 线快照查询职责](kline-snapshot-queries.md)：DojoAgents 与 DojoSDK 的职责边界。
- [Session 设计与集成](session-history.md)：运行时会话生命周期和 Dashboard 集成。
- [外部 SessionStore / BlobStore 适配器](session-store-adapter.md)：持久化适配器契约与一致性验收。
- [异步运行时](async-runtime.md)：AnyIO 边界、TaskGroup 所有权、超时与取消、线程与内存限界、
  SSE 跨线程桥接、子进程回收与 asyncio 兼容白名单。
- [Provider 请求边界](provider-request-boundary.md)：内部消息、OpenAI-compatible wire 策略与出站适配器职责。

跨组件的整体关系放在 **架构**；尚未完成的提案、迁移步骤和历史决策放在 **计划**。
