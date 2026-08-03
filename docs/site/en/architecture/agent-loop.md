# Agent Loop

!!! tip "Looking for the real implementation?"
    This page is the **conceptual** view of a turn. In code, the loop kernel is [Strands Agents](https://github.com/strands-agents/sdk-python); DojoAgents plugs its own stack in through a model bridge, a tool bridge and hooks.
    For the full walk-through (framework choice, the seven stages of `run()`, system-prompt composition, guardrail/compaction/harness interception, code index) see **[Agent Internals](agent-internals.md)**.

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

