# 预计算行业数据

## 适用场景

行业预计算用于降低 Dashboard 查询板块数据时的实时 K 线调用压力。生成的数据会保存在 `dojo_sector_precomputed` 目录中，供 `SectorPrecomputedStore` 加载。

## 命令

```bash
dojoagents precompute-sector
```

可选参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--data-root` | Dashboard data root | 输出数据根目录 |
| `--start-date` | `2025-01-01` | 起始交易日 |
| `--upload` | `false` | 上传发布快照 |

## 产物

- `constituents.parquet`
- `sector_daily.parquet`
- `ticker_daily.parquet`

## 深入阅读

完整说明后续应继续补充到本页，避免维护第二套功能指南。
