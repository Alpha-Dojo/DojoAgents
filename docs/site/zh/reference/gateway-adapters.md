# Gateway Adapters

## 状态

Gateway adapter 位于 `dojoagents/gateway/adapters/`，注册入口在 `dojoagents/gateway/registry.py`。

## 当前平台

常见 adapter 包括：

- Slack
- WeChat
- WeCom
- Feishu
- Discord
- Telegram

## Adapter 责任

Adapter 应负责：

- 解析平台 webhook。
- 规范化为通用 gateway event。
- 发送 Agent 回复。
- 处理目标 ID、认证和平台错误。

## 配置

Adapter 配置保存在 `~/.dojo/agents.yaml` 的 `gateway.hooks` 下。推荐使用：

```bash
dojoagents gateway setup all
```

