# DojoSDK

## 原则（Agent 金融取数）

1. **Agent / Task 的金融只读主路径是 `dojo.sdk.*`**（经 `dojoagents/tools/dojo_sdk_tool.py` → `AsyncDojo`，HF offline / qdata）。
2. **Dashboard domain tools / HTTP API 是产品 UI 面**，不是 Task 的依赖。新金融只读能力优先补进 SDK，而不是 `dashboard/tools/domain_tools.py`。
3. **Precompute 产物经 SDK precomputed tools 消费**：`dojoagents precompute-sector*` → `dojo_sector_precomputed` → `dojo.sdk.sector.precomputed_*`。

非金融工具（`web_search` / `web_extract`、`write_session_file` / `read_session_output`）保持独立工具族，不进入本页清单。

## 状态

DojoAgents 通过 `dojosdk` 依赖和 `dojoagents/tools/dojo_sdk_tool.py` 暴露金融数据工具。  
`get_dojo_sdk_specs()` 只注册 `OFFLINE_TOOL_BINDINGS` 中且同时存在于 `HF_REGISTRY` 的条目。

Dashboard 服务层仍可通过 domain services / Dojo data gateway 服务 UI；那条链路与 Agent SDK 工具解耦。

## 相关配置

DojoSDK 依赖由 `pyproject.toml` 管理。当前项目可使用本地 source 覆盖：

```toml
[tool.uv.sources]
dojosdk = { path = "../DojoSDK" }
```

相关配置字段：

| 字段 | 说明 |
| --- | --- |
| `dojosdk` (`DojoSDKConfig`) | API key、base_url、timeout、retries |
| `dashboard.financial.sdk_cache_dir` | HF hub 缓存目录（默认 `~/.cache/huggingface/hub`） |

## 数据流

```text
precompute-sector / precompute-sector-theme-state
        │
        ▼
dojo_sector_precomputed/   (constituents, sector_daily, ticker_daily,
                            theme_state_daily, horizon, alpha factors, …)
        │
        ▼
AsyncDojo (HF offline / qdata)
        │
        ▼
dojo.sdk.*  ToolSpec  ←── Agent / Task（目标主路径）
```

```text
Dashboard UI / REST (/api/v1/…)
        │
        ▼
FinancialDomainRegistry / stores
        │
        └── 可与同一预计算包同源，但 Agent Task 不应再依赖 domain_tools
```

## 已注册 `dojo.sdk.*` 工具

| Tool | 能力 | 典型用途 |
| --- | --- | --- |
| `dojo.sdk.sector.info` | 板块 taxonomy（name / level / parent_id） | 弱定位；**不宜**作为预计算 L1/L2/L3 主定位器 |
| `dojo.sdk.sector.symbol_relations` | 板块↔股票关系 | 粗粒度成分关系 |
| `dojo.sdk.sector.precomputed_sector_alpha_factors_daily` | 按 date/market/L1–L3 查板块 alpha | Theme Drivers / Risks 定量侧证 |
| `dojo.sdk.sector.precomputed_ticker_alpha_factors_daily` | 按 date/market/ticker/L1–L3 查个股 alpha | Top Components 排序辅助 |
| `dojo.sdk.stock.news` | 单票新闻（page / page_size） | 成分股新闻（缺日期窗，宜增强） |
| `dojo.sdk.stock.event_remind` | 单票事件提醒 | 公司事件辅助 |
| `dojo.sdk.stock.ystock_info` | 股票画像 | 行业/角色辅助 |
| `dojo.sdk.stock.current_quote` | 当前报价 | 实时场景；历史交易日解读帮助有限 |
| `dojo.sdk.stock.kline` | 个股 K 线 | 单票走势；不适合整板块贡献度 |
| `dojo.sdk.stock.fin_indicators` | 财务指标 | 基本面点缀 |
| `dojo.sdk.stock.main_income` | 主营构成 | 可选 |
| `dojo.sdk.benchmark.kline` | 基准指数 K 线 | 相对大盘（不如 benchmark daily） |
| `dojo.sdk.analysis.market_dynamics` | 市场动态分析记录 | 宏观背景可选 |
| `dojo.sdk.forex.kline` | 外汇 K 线 | 与板块主题任务基本无关 |

代码入口：`dojoagents/tools/dojo_sdk_tool.py`（`OFFLINE_TOOL_BINDINGS`）。

## 待补能力（相对 Dashboard domain tools / Theme Deep Dive） {#sdk-gaps}

### P0 — Theme Deep Dive / 最小 trigger 闭环

最小输入：`trading_date + market + (level1_id+level2_id+level3_id | sector_name)`。  
其余字段（涨跌幅、方向、规范中英文名、成分贡献）由取数回填。

| 建议能力 | 替代的 Dashboard 能力 | 说明 |
| --- | --- | --- |
| `resolve_sector` / taxonomy 搜索（对齐预计算 L1/L2/L3） | `search_sector_taxonomy`、`get_taxonomy_tree` | name→唯一 L3；多候选返回；ID 存在性校验 |
| `precomputed_sector_daily`（带过滤） | `get_sector_movers` / 分析接口的当日涨跌 | 回填 `change_percent` / `direction` |
| `precomputed_constituents`（带过滤） | `filter_sector_constituents` 名单 | 成分、权重、角色 |
| `precomputed_ticker_daily`（带过滤）或合并 `get_sector_members_with_returns` | 成分股 + 当日收益 | Top Components / 新闻名单 |
| `get_sector_contribution_leaders`（或 SDK 内聚合） | movers 中的 leader concentration | `top_contributors` / `rally_type` |
| `stock.news` 日期窗增强，或 `get_sector_constituent_news` | `get_ticker_news_and_events`（新闻） | Top-K 批量 + 去重 + `[T-2,T]` |

实现提示：`DojoSDKToolManager` 中已有部分 precomputed handler（如 constituents / sector_daily / ticker_daily / theme_state），但未进入 `OFFLINE_TOOL_BINDINGS`，且多为整表拉取；需改为可过滤查询后再注册。

### P1 — Drivers / Risks 质量

| 建议能力 | 说明 |
| --- | --- |
| `precomputed_theme_state_daily`（带过滤） | breadth / RS / rotation / `stage_hint` |
| `precomputed_sector_horizon_metrics`（带过滤） | 中长期动量、回撤、估值分位 |
| `precomputed_market_benchmark_daily`（带过滤） | 相对大盘 |
| 股票事件（带日期） | 对齐公司公告/财报证据 |

### P2 — 若 `daily-market-events` 也迁到纯 SDK

| 建议能力 | 替代 |
| --- | --- |
| `get_market_overview` 等价 | `get_market_overview` |
| `get_sector_movers` 等价 | `get_sector_movers` |

### 明确不进 SDK

| 能力 | 原因 |
| --- | --- |
| `web_search` / `web_extract` | 独立 Web 工具族 |
| `write_session_file` / `read_session_output` | Task 产物 IO |
| Portfolio 写工具 | 另一产品面；可暂留 `dashboard/tools/portfolio_tools.py` |

## 错误边界

Dashboard 的 Dojo data gateway error family 位于 `dojoagents/dashboard/services/dojo_data_gateway.py`：

- `GatewayError`
- `GatewayBadResponseError`
- `GatewayTimeoutError`
- `GatewayUnavailableError`
- `GatewayResult`

## 相关页面

- [任务与流水线](../user-guide/tasks-and-pipelines.md)
- [金融工作流](../user-guide/financial-workflows.md)
- [CLI Reference](cli.md)
- [Tool Contracts](tool-contracts.md)
- [添加工具](../development/adding-tools.md)

## 深入阅读

旧版集成说明的核心内容已并入本页；迁移与能力盘点见 `docs/plans/`（不进站点导航）。
