# Gateway Adapters

Gateway adapters live under `dojoagents/gateway/adapters/` and are registered in `dojoagents/gateway/registry.py`.

Common platforms include Slack, WeChat, WeCom, Feishu, Discord, and Telegram.

Adapters should parse platform webhooks, normalize events, send replies, and handle authentication and platform-specific errors.

