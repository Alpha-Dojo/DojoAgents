# Event-driven

## 目标

事件驱动架构用于把 Agent、工具、计划任务、多代理、Dashboard SSE 和自动化触发器解耦。

## 当前事件面

- `dojoagents/agent/events.py` 定义 Agent event。
- `dojoagents/dashboard/sse.py` 将 Agent event 包装进 OpenAI chunk。
- `dojoagents/utils/event_bus.py` 提供通用事件总线。
- `dojoagents/multi_agent/triggers.py` 和 `dojoagents/planning/triggers.py` 处理自动触发。

## 设计原则

- 事件应该有稳定 `run_id`、`seq` 和时间戳。
- 工具开始和结束事件应通过 `call_id` 匹配。
- 前端应按事件 reducer 消费，而不是按工具名称猜状态。

## 深入阅读

- [dojo.v2 协议](../reference/dojo-v2-protocol.md)
- [Dashboard API](../reference/dashboard-api.md)
