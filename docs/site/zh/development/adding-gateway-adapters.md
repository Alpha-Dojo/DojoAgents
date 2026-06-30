# 添加 Gateway Adapter

## 标准路径

1. 在 `dojoagents/gateway/adapters/<platform>.py` 添加 adapter。
2. 遵循或继承 `BaseGatewayAdapter`。
3. 在 `dojoagents/gateway/registry.py` 注册。
4. 添加配置字段和测试。

## Adapter 责任

- 将平台 webhook 转换为通用 `GatewayEvent`。
- 将 Agent 回复发送回平台。
- 处理认证、目标 ID、平台错误和重试。
- 不要把平台特有逻辑泄漏进 Agent core。

## 用户配置

推荐让用户通过：

```bash
dojoagents gateway setup <adapter>
```

生成所需配置。

