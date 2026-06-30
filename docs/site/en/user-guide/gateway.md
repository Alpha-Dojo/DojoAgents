# Gateway

The gateway normalizes messages from Slack, Telegram, WeChat, WeCom, Feishu, Discord, and similar chat platforms into DojoAgents requests, then sends agent replies back to the target platform.

## Start

```bash
dojoagents gateway --host 127.0.0.1 --port 8766
```

Service endpoints:

```text
GET  /api/health
GET  /api/platforms
POST /api/webhook/{platform}
POST /api/send/{platform}/{target}
```

Default config file:

```text
~/.dojo/agents.yaml
```

## Configure Adapters

Configure all adapters:

```bash
dojoagents gateway setup all
```

Configure one adapter:

```bash
dojoagents gateway setup telegram
dojoagents gateway setup slack
dojoagents gateway setup discord
dojoagents gateway setup feishu
dojoagents gateway setup wecom
dojoagents gateway setup wechat
```

The setup command writes to `gateway.hooks`. Each platform has different token, secret, webhook URL, and target ID requirements; follow the interactive prompts.

## Pairing

Some platforms require explicit approval between an external user and the local agent:

```bash
dojoagents gateway pairing list
dojoagents gateway pairing approve telegram PAIRING_CODE
dojoagents gateway pairing deny telegram PAIRING_CODE
```

Filter by platform:

```bash
dojoagents gateway pairing list --platform telegram
```

The pairing store path comes from `gateway.pairing_store`; when unset, the gateway uses its default state directory.

## Security Boundaries

- Prefer binding the gateway to `127.0.0.1` and exposing webhooks through a reverse proxy or tunnel.
- Platform tokens, signing secrets, and bot secrets must not be written to docs or logs.
- Public webhooks should use platform signature verification, access controls, and rate limiting.
- Pairing codes are for authorization flow only and should not be reused long-term.

## Troubleshooting

Platform does not receive replies:

- Confirm `dojoagents gateway` is still running.
- Confirm the platform webhook points to `/api/webhook/{platform}`.
- Confirm adapter token/secret and target ID values.

Gateway does not receive messages:

- Check that the public callback URL reaches the local service.
- Check whether the platform requires HTTPS.
- Check platform signature or challenge verification.

Pairing approval needed:

- Run `dojoagents gateway pairing list`.
- Use `approve` for trusted users and `deny` for unknown users.

## Related Pages

- [Gateway Architecture](../architecture/gateway.md)
- [Gateway Adapters Reference](../reference/gateway-adapters.md)
- [Configuration](../reference/configuration.md)
