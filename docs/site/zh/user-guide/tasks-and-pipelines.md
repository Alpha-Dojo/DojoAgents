# 任务与流水线

## 适用场景

结构化 Task 用于可重复的金融批处理：给定交易日（或板块），按固定工具顺序取证，再按 JSON Schema 写出产物。  
与自由聊天 Agent 不同，Task 有 `contract.yaml`、`TASK.md`、产物 schema，以及可选 pipeline 串联。

## 入口

```bash
# 跑流水线（示例：每日市场事件）
dojoagents tasks run --pipeline daily-market-events --date 2026-07-22

# 校验某 task 当日产物是否符合 schema
dojoagents tasks eval --task event-trigger --date 2026-07-22
```

配置：`tasks.enabled`、`tasks.output_root`（默认产物在 `~/.dojo/tasks/outputs/<task-id>/`）。  
详见 [CLI Reference](../reference/cli.md)。

代码根：`dojoagents/tasks/`（`built_in/`、`pipelines/`、manager / activator / schema_validator）。

## 工具策略（目标态）

| 类别 | 用途 | 说明 |
| --- | --- | --- |
| `dojo.sdk.*` | 金融只读取数 | **主路径**；见 [DojoSDK](../reference/dojo-sdk.md) |
| `web_search` / `web_extract` | 外网新闻证据 | 独立工具族 |
| `write_session_file` / `read_session_output` | 任务产物读写 | Session / task output 工具 |

**不再把 Dashboard domain tools（如 `get_sector_movers`、`search_sector_taxonomy`）作为新 Task 的依赖。**  
现有 `daily-market-events` 在迁移完成前仍可能引用 domain tools；新流水线（Theme Deep Dive）按 SDK 设计。

## 现有流水线：`daily-market-events`

```text
sector-attribution  →  market_news_raw_pack_{date}.json
        │
        ▼
event-trigger       →  market_event_triggers_{date}.jsonl
```

| Task | Harness | 职责 |
| --- | --- | --- |
| `sector-attribution` | `tool_orchestrated` | 筛异动板块，检索可解释新闻，写原始素材包 |
| `event-trigger` | `artifact_synthesis` | 读素材包，合成事件卡 + `sector_impacts` |

定义：

- `dojoagents/tasks/pipelines/daily-market-events.yaml`
- `dojoagents/tasks/built_in/sector-attribution/`
- `dojoagents/tasks/built_in/event-trigger/`

该流水线是 **全市场事件视角**，与下方「单板块主题深挖」独立，不共享新闻 pack。

## 设计中：Theme Deep Dive（板块主题深挖）

### 目标

对 Daily Discovery / 用户已锁定的单个板块（例如 CN 半导体当日 +7.7%），产出：

- Key Drivers
- News Event Impact（含正负向与 impact 分）
- Key Risks
- Top Components

### 最小 Trigger

```text
必填:
  trading_date
  market: cn | us | hk
  且二选一:
    A) level1_id + level2_id + level3_id
    B) sector_name

禁止依赖调用方传入 change_percent / direction（取数回填）
```

定位规则：

- 传 ID → 校验存在；不存在则失败（不静默模糊匹配）
- 传 name → taxonomy 搜索；唯一高置信命中则锁定；多候选或不命中则失败/返回 candidates
- 默认粒度 **L3**

### 推荐两段 Task（独立 pipeline）

```text
theme-deep-dive
  sector-theme-research   (tool_orchestrated)
        → sector_theme_research_pack_{…}.json
  sector-theme-synthesis  (artifact_synthesis)
        → theme_deep_dive_{…}.json
```

与 `daily-market-events` **完全独立**：新闻重新获取，不读对方产物。

### Research 阶段

1. **Quant**：板块当日涨跌、成分股收益、贡献度 Top-N、`rally_type`；可选 theme_state / alpha。  
2. **News（双通道）**  
   - 通道 A：按贡献度拉 Top-K 成分股新闻 / 事件（优先 SDK 批量+日期窗）  
   - 通道 B：板块主题 `web_search` / `web_extract`  
3. 只写证据 pack，不写最终四卡片文案。

### Synthesis 阶段

只读 research pack，输出四卡片 JSON；硬约束：

- 不改写取数得到的 `change_percent` / 成分股白名单  
- 每条 Driver / Impact / Risk 绑定 `evidence_ids`  
- `top_components` ⊆ quant `top_contributors`

所需 SDK 能力见 [DojoSDK 待补清单](../reference/dojo-sdk.md#sdk-gaps)。

## 相关页面

- [DojoSDK](../reference/dojo-sdk.md)
- [金融工作流](financial-workflows.md)
- [CLI](../reference/cli.md)
- [Tool Contracts](../reference/tool-contracts.md)
