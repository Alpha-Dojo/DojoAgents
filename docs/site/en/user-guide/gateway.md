# Gateway

The gateway normalizes messages from chat platforms into DojoAgents requests and sends agent replies back to those platforms.

## Start

```bash
dojoagents gateway --host 127.0.0.1 --port 8766
```

## Configure Adapters

```bash
dojoagents gateway setup all
```

Single adapter:

```bash
dojoagents gateway setup telegram
dojoagents gateway setup slack
dojoagents gateway setup discord
dojoagents gateway setup feishu
dojoagents gateway setup wecom
dojoagents gateway setup wechat
```

## Pairing

```bash
dojoagents gateway pairing list
dojoagents gateway pairing approve telegram PAIRING_CODE
dojoagents gateway pairing deny telegram PAIRING_CODE
```

