# Security

## Secrets

Do not expose API keys, provider tokens, webhook secrets, or sensitive user configuration in docs, logs, dashboard responses, memory, or tool results.

## Tool Execution

Tools must execute through `ToolExecutor` and sandbox policy. Do not bypass `SandboxPolicy`.

## Dashboard

If the dashboard binds to `0.0.0.0` or is exposed publicly, add authentication, access control, and network isolation.

