# Event-driven Architecture

Event-driven architecture decouples agents, tools, planning, multi-agent flows, dashboard SSE, and automation triggers.

## Event Surfaces

- `dojoagents/agent/events.py`
- `dojoagents/dashboard/sse.py`
- `dojoagents/utils/event_bus.py`
- `dojoagents/multi_agent/triggers.py`
- `dojoagents/planning/triggers.py`

Events should include stable identifiers such as `run_id`, `seq`, timestamp, and `call_id` for tool correlation.

