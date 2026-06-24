# Precompute Sector Daily 数据使用指南

## 背景说明

为了优化 AlphaDojo Dashboard 获取板块数据时的性能并降低对实时 K 线服务的调用压力，我们将所有支持的板块成份股及每日行情（从 2025-01-01 至今）预计算并导出为本地的 Parquet 文件格式。这些文件将作为离线数据集 `dojo_sector_precomputed` 提供给下游（如 DojoAgents API）直接使用。

核心代码位于：
- **功能模块：** `dojoagents/dashboard/services/precompute_sector_daily.py`
- **CLI 执行命令：** `dojoagents precompute-sector`

---

## 1. 命令行执行 (CLI 命令)

您可以直接运行 CLI 命令来手动生成板块预计算数据：

```bash
# 激活环境
source .venv/bin/activate
export PYTHONPATH=.

# 执行命令
dojoagents precompute-sector
```

### 可选参数

| 参数名 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data-root` | Path | `FinancialDashboardConfig.dashboard_data_root` | 指定输出数据的根目录。Parquet文件会保存在此目录下的 `dojo_sector_precomputed` 子目录中。 |
| `--start-date` | str | `2025-01-01` | 指定统计 K 线数据的起始时间，格式为 `YYYY-MM-DD`。 |

**执行输出示例：**
```
Precomputing sector data -> /Users/.../.dojo/dashboard-data/dojo_sector_precomputed
Window start: 2025-01-01
{
  "version": "2",
  "generated_at": "2026-06-23T16:00:00Z",
  "latest_dates": {
    "us": "2026-06-22",
    "sh": "2026-06-23",
    "hk": "2026-06-23"
  }
}
```
命令执行完毕后，指定目录下会生成 `constituents.parquet`，`sector_daily.parquet`，以及 `ticker_daily.parquet` 三个文件。

---

## 2. 在代码中集成调用

如果您希望在定时任务或后台任务（例如闭盘后的调度器）中调用此方法，可以直接引入 `build_sector_precomputed` 函数。

### 核心函数签名

```python
from dojoagents.dashboard.services.precompute_sector_daily import build_sector_precomputed

def build_sector_precomputed(
    *,
    data_root: Path,
    sector_store: StockSectorStore,
    stock_store: StockStore,
    kline_store: KlineStore,
    start_date: str = "2025-01-01",
    out_dir: Path | None = None,
) -> dict:
```

### 示例代码

以下代码展示了如何在后台协程中调用并生成预计算数据：

```python
import asyncio
from pathlib import Path
from dojoagents.dashboard.services.precompute_sector_daily import build_sector_precomputed

async def trigger_precompute(store_registry, data_root: Path):
    # 鉴于该函数涉及大量 pandas 计算，建议通过 asyncio.to_thread 在后台线程执行
    manifest = await asyncio.to_thread(
        build_sector_precomputed,
        data_root=data_root,
        sector_store=store_registry.stock_sector_store,
        stock_store=store_registry.stock_store,
        kline_store=store_registry.kline_store,
    )
    
    # 打印生成的元数据
    print(manifest)
```

---

## 3. 生成产物解析

`precompute_sector_daily` 成功运行后，会生成以下三个 Parquet 格式的离线文件：

1. **`constituents.parquet`** 
   - **内容：** 记录所有市场下、各个行业板块（L1/L2/L3）当前的成分股及其市值。
   - **核心列：** `level1_id`, `level2_id`, `level3_id`, `market`, `ticker`, `market_cap`

2. **`sector_daily.parquet`** 
   - **内容：** 记录各行业板块从 `start_date` 至今每一天的总市值与等权收益率（板块层面的行情）。
   - **核心列：** `scope`, `level1_id`, `level2_id`, `level3_id`, `market`, `trade_date`, `index_level`, `daily_return_pct`, `total_market_cap`, `member_count`

3. **`ticker_daily.parquet`** 
   - **内容：** 记录对应成份股从 `start_date` 至今每天的收盘价与累计/单日涨跌幅。
   - **核心列：** `ticker`, `trade_date`, `close`, `daily_return_pct`, `cumulative_return_pct`

这些文件将被供 `SectorPrecomputedStore` 在服务启动或热更新时载入内存（`pandas.DataFrame`），以实现 O(1) 或 O(log N) 级的数据查询。
