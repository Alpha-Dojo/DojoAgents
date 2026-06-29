# 仓库地图

## 目标

本页帮助维护者快速找到扩展点，避免重复实现已有基础设施。

## 主要目录

| 目录 | 说明 |
| --- | --- |
| `dojoagents/agent/` | Agent loop、runtime、provider、events、guardrails |
| `dojoagents/config/` | ConfigStore 和配置 schema |
| `dojoagents/tools/` | Tool registry、executor、sandbox 和工具实现 |
| `dojoagents/dashboard/` | FastAPI Dashboard、services、schemas、React app |
| `dojoagents/gateway/` | Gateway server、runner、state、adapters |
| `dojoagents/plugins/` | Plugin discovery、hooks、manifest |
| `dojoagents/skills/` | Skill loader、cache、manager |
| `dojoagents/memory/` | Memory provider 和 manager |
| `dojoagents/multi_agent/` | Agent pool 和 delegation |
| `dojoagents/planning/` | Plan store、engine、tools、triggers |
| `dojoagents/quant/` | Quant context、risk、workflow |
| `tests/` | Pytest suite |
| `docs/` | MkDocs 文档和历史设计记录 |

## 必须复用的基础设施

- 配置：`ConfigStore`
- 日志：`dojoagents.logging`
- 工具：`ToolRegistry`、`ToolSpec`、`ToolExecutor`
- Dashboard 存储：`AtomicJsonStore`、`AtomicJsonlStore`
- Dashboard services：通过 `dojoagents/dashboard/deps.py` 获取

