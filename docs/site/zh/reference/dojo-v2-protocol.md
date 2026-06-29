# dojo.v2 协议

## 状态

`dojo.v2` 是 DojoAgents 在 OpenAI-compatible streaming chunk 上附加 typed event 的协议层。

## 事件要求

事件应包含：

- `schema_version`
- `run_id`
- `seq`
- `session_id`
- `timestamp`
- `type`

工具事件还应使用 `call_id` 关联 `tool_start` 和 `tool_result`。

## 常见事件

- `phase`
- `delta`
- `tool_start`
- `tool_result`
- `eval_hint`
- `done`
- `error`

## 工具结果扩展

`tool_result` 可携带：

- `data`
- `viz_blocks`
- `artifacts`
- `resource_changes`
- `truncated`
- `latency_ms`

## 深入阅读

旧版协议说明的核心内容已并入本页；后续协议细节应优先更新当前 Reference 页面。
