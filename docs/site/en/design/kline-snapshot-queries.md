# K-line snapshot query ownership

DojoAgents does not preload or index the complete offline K-line dataset.
DojoSDK owns snapshot synchronization, Parquet scanning, filtering, per-symbol
limits, ordering, and price adjustment.

`DojoDataGateway.stock_klines()` selects the SDK surface by client mode:

- offline clients use one bounded `client.stocks.get_klines()` batch request;
- online clients retain concurrent per-symbol `get_kline()` requests because
  the online service cannot return local snapshot metadata.

The offline gateway maps `start_time`, `end_time`, `limit`, and
`price_adj_type` to `start`, `end`, `limit_per_symbol`, and `adjust`. It stores
the returned `SnapshotMetadata` in `GatewayResult.snapshot`. K-line consumers
must carry this identity with cached or derived results and must not read a
second "current revision" after a query completes.

`KlineStore` keeps only a bounded cache of assembled responses. It records the
last observed snapshot metadata and clears that cache when a later SDK result
contains a different `snapshot_token`. It does not persist raw K-lines, build a
full-market DataFrame, maintain a symbol index, or apply prices a second time.
