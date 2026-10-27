# K 线快照查询职责

DojoAgents 不预加载或索引完整的离线 K 线数据集。快照同步、Parquet 扫描、过滤、每个 symbol 的条数限制、排序和复权统一由 DojoSDK 负责。

`DojoDataGateway.stock_klines()` 根据客户端模式选择 SDK 接口：

- 离线客户端通过一次有界的 `client.stocks.get_klines()` 批量请求读取数据。
- 在线客户端继续并发调用每个 symbol 的 `get_kline()`，因为在线服务不会返回本地快照元数据。

离线 Gateway 将 `start_time`、`end_time`、`limit` 和 `price_adj_type` 映射为 `start`、`end`、`limit_per_symbol` 和 `adjust`，并把返回的 `SnapshotMetadata` 保存在 `GatewayResult.snapshot` 中。K 线消费者必须让缓存或派生结果携带这份快照身份，查询结束后不得再次读取另一个“当前 revision”来替代它。

`KlineStore` 只保存有界的最终响应缓存。它记录最近一次观察到的快照元数据；当后续 SDK 结果包含不同的 `snapshot_token` 时清空缓存。它不得持久化原始 K 线、构建全市场 DataFrame、维护 symbol 索引或再次执行复权。
