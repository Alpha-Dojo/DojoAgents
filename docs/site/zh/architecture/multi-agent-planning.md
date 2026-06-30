# Multi-Agent 与 Planning

## 目标

Multi-Agent 和 Planning 模块让 DojoAgents 能够创建子代理、委派任务、保存计划、执行计划步骤，并通过事件触发自动化流程。

## 模块

| 模块 | 说明 |
| --- | --- |
| `dojoagents/multi_agent/models.py` | Agent 和 delegation 数据模型 |
| `dojoagents/multi_agent/pool.py` | Agent pool |
| `dojoagents/multi_agent/orchestrator.py` | 多代理编排 |
| `dojoagents/multi_agent/tools.py` | 委派工具 |
| `dojoagents/planning/models.py` | Plan 数据模型 |
| `dojoagents/planning/store.py` | Plan 状态存储 |
| `dojoagents/planning/engine.py` | Plan 执行引擎 |
| `dojoagents/planning/tools.py` | Plan 工具 |

## 设计边界

Multi-Agent 不应替代通用 Agent Loop。它是更高层的编排能力，用于把复杂任务拆分给不同代理或计划步骤。

## 深入阅读

- [Event-driven](event-driven.md)
- [配置](../reference/configuration.md)
