# 仓库地图

## 目标

本页帮助维护者快速找到扩展点，避免重复实现已有基础设施。

## 主要目录

| 目录 | 说明 |
| --- | --- |
| `dojoagents/agent/` | Agent loop、runtime、provider、events、guardrails；含 `harnesses/`（领域约束）、`hooks/`（循环切面），实现剖析见 [Agent 实现内幕](../architecture/agent-internals.md) |
| `dojoagents/config/` | ConfigStore 和配置 schema |
| `dojoagents/tools/` | Tool registry、executor、sandbox；含 `dojo_sdk_tool.py`、web、session |
| `dojoagents/tasks/` | 结构化 Task / Pipeline（contract、TASK.md、schema、pipelines） |
| `dojoagents/dashboard/` | FastAPI Dashboard、services、schemas、React app；`dashboard/tools/` 为 portfolio / legacy domain |
| `dojoagents/gateway/` | Gateway server、runner、state、adapters |
| `dojoagents/plugins/` | Plugin discovery、hooks、manifest |
| `dojoagents/skills/` | Skill loader、cache、manager |
| `dojoagents/memory/` | Memory provider 和 manager |
| `dojoagents/multi_agent/` | Agent pool 和 delegation |
| `dojoagents/planning/` | Plan store、engine、tools、triggers |
| `dojoagents/quant/` | Quant context、risk、workflow |
| `tests/` | Pytest suite |
| `docs/` | MkDocs 正式文档和 `docs/plans/` 历史规划材料 |

## 必须复用的基础设施

- 配置：`ConfigStore`
- 日志：`dojoagents.logging`
- 工具：`ToolRegistry`、`ToolSpec`、`ToolExecutor`
- Agent 循环：复用 `AgentLoop` 与 Strands 内核，不要另起循环；扩展请走 tool / harness / hook / plugin（见 [Agent 实现内幕](../architecture/agent-internals.md) 的扩展点速查）
- 金融 Agent 只读：优先 `dojo.sdk.*`（见 [DojoSDK](../reference/dojo-sdk.md)）
- Dashboard 存储：`AtomicJsonStore`、`AtomicJsonlStore`
- Dashboard services：通过 `dojoagents/dashboard/deps.py` 获取
