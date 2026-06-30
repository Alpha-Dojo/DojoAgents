# Agent Loop

## 目标

Agent Loop 负责一轮或多轮模型调用、工具调用、工具结果回填和最终回答生成。

## 核心对象

| 对象 | 说明 |
| --- | --- |
| `ChatRequest` | Agent 输入请求 |
| `ToolCall` | 模型请求的工具调用 |
| `ToolResult` | 工具执行结果 |
| `LLMResult` | provider 返回的模型内容和工具调用 |
| `AgentResponse` | Agent 最终响应 |

## 流程

1. 接收 `ChatRequest`。
2. 构造模型上下文。
3. 调用 provider。
4. 将 provider tool calls 转为 `ToolCall`。
5. 通过 `ToolExecutor.execute_one()` 执行工具。
6. 将工具结果转回模型上下文，必要时继续循环。
7. 输出 `AgentResponse` 和事件流。

## Harness 边界

金融任务、组合验证、最终回答质量控制等领域逻辑不应硬编码在通用 Agent Loop 中。它们应通过 harness、tools、presenters 或插件参与流程。

## 相关代码

- `dojoagents/agent/loop.py`
- `dojoagents/agent/models.py`
- `dojoagents/agent/events.py`
- `dojoagents/tools/executor.py`

