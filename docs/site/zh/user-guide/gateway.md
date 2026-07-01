# Gateway

Gateway 把 Slack、Telegram、WeChat、WeCom、Feishu、Discord 等聊天平台消息标准化为 DojoAgents 请求，并把 Agent 回复发回目标平台。

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

默认配置文件：

```text
~/.dojo/agents.yaml
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

配置结果写入 `gateway.hooks`。不同平台需要的 token、secret、webhook URL、目标 ID 不同，按交互式提示填写。

## 配对管理

部分平台需要把外部用户和本地 Agent 授权关系配对：

```bash
dojoagents gateway pairing list
dojoagents gateway pairing approve telegram PAIRING_CODE
dojoagents gateway pairing deny telegram PAIRING_CODE
```

可按平台过滤：

```bash
dojoagents gateway pairing list --platform telegram
```

pairing store 路径来自 `gateway.pairing_store`，未配置时使用默认 gateway 状态目录。

## 安全边界

- Gateway 默认建议绑定 `127.0.0.1`，由反向代理或隧道服务暴露 webhook。
- 平台 token、signing secret 和 bot secret 不应写入文档或日志。
- 对公网 webhook 建议配置平台签名校验、访问控制和限流。
- Pairing code 只用于授权流程，不要长期复用。

## 常见问题

平台收不到回复：

- 确认 `dojoagents gateway` 仍在运行。
- 检查平台 webhook 是否指向 `/api/webhook/{platform}`。
- 确认 adapter token/secret 和目标 ID 正确。

Gateway 收不到消息：

- 检查公网回调地址是否能访问到本地服务。
- 检查平台是否要求 HTTPS。
- 检查平台签名或 challenge 流程是否完成。

需要批准 pairing code：

- 运行 `dojoagents gateway pairing list` 查看待批准项。
- 对可信用户运行 `approve`，对未知用户运行 `deny`。

## 深入阅读

- [Gateway 架构](../architecture/gateway.md)
- [Gateway Adapters Reference](../reference/gateway-adapters.md)
- [配置](../reference/configuration.md)
