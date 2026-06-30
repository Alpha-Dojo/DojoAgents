# Gateway

## 适用场景

Gateway 把 Slack、Telegram、WeChat、Feishu、Discord 等聊天平台消息标准化为 DojoAgents 的请求，并把 Agent 回复发回目标平台。

## 启动服务

```bash
dojoagents gateway --host 127.0.0.1 --port 8766
```

服务入口：

```text
GET  /api/health
GET  /api/platforms
POST /api/webhook/{platform}
POST /api/send/{platform}/{target}
```

## 配置 Adapter

配置所有 adapter：

```bash
dojoagents gateway setup all
```

配置单个 adapter：

```bash
dojoagents gateway setup telegram
dojoagents gateway setup slack
dojoagents gateway setup discord
dojoagents gateway setup feishu
dojoagents gateway setup wecom
dojoagents gateway setup wechat
```

默认配置路径：

```text
~/.dojo/agents.yaml
```

## 配对管理

```bash
dojoagents gateway pairing list
dojoagents gateway pairing approve telegram PAIRING_CODE
dojoagents gateway pairing deny telegram PAIRING_CODE
```

## 深入阅读

- [Gateway 架构](../architecture/gateway.md)
- [Gateway Adapters Reference](../reference/gateway-adapters.md)
- 后续补充：将旧版使用说明中仍有价值的示例继续收敛到本页
