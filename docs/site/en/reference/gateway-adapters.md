# Gateway Adapters

Gateway adapters live under `dojoagents/gateway/adapters/` and are registered through `dojoagents/gateway/registry.py`.

## Platforms

The default registry includes:

- Slack
- WeChat
- WeCom
- Feishu
- Discord
- Telegram

## Adapter Responsibilities

Adapters should:

- parse platform webhooks;
- normalize platform messages into common gateway events;
- send agent replies back to the correct target;
- handle authentication, target IDs, and platform-specific errors;
- return structured send/normalize results instead of leaking platform response shapes.

## Configuration

Adapter configuration is stored under `gateway.hooks` in `~/.dojo/agents.yaml`. The recommended setup path is:

```bash
dojoagents gateway setup all
```

Use one adapter name to configure only that platform:

```bash
dojoagents gateway setup telegram
```

## Pairing

When an adapter requires user approval, use:

```bash
dojoagents gateway pairing list
dojoagents gateway pairing approve telegram CODE
dojoagents gateway pairing deny telegram CODE
```

## Code Anchors

- `dojoagents/gateway/adapters/base.py`
- `dojoagents/gateway/adapters/__init__.py`
- `dojoagents/gateway/registry.py`
- `dojoagents/cli/gateway_setup.py`
