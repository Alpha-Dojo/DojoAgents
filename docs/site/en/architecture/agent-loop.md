# Agent Loop

The agent loop coordinates model calls, tool calls, tool result feedback, and final answer generation.

## Core Objects

| Object | Purpose |
| --- | --- |
| `ChatRequest` | Agent input |
| `ToolCall` | Model-requested tool call |
| `ToolResult` | Tool execution result |
| `LLMResult` | Provider response |
| `AgentResponse` | Final agent response |

Finance-specific validation and harness logic should stay outside the generic loop and be implemented through tools, harnesses, presenters, or plugins.

