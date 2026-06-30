# Gateway 架构

## 目标

Gateway 将聊天平台的 webhook 事件标准化，转换为 DojoAgents 请求，并负责把响应发送回目标平台。

## 组件

| 组件 | 说明 |
| --- | --- |
| `gateway/server.py` | Gateway FastAPI app |
| `gateway/runner.py` | Gateway runtime runner |
| `gateway/registry.py` | Adapter registry |
| `gateway/adapters/` | 平台 adapter |
| `gateway/state.py` | SQLite session/gateway state |
| `gateway/pairing.py` | 用户配对 |

## Adapter 边界

新增 adapter 应遵循 `BaseGatewayAdapter` 的接口，负责：

- 规范化平台消息为 `GatewayEvent`。
- 发送文本或结构化消息。
- 处理平台认证、目标 ID 和错误。

## 相关页面

- [Gateway 用户指南](../user-guide/gateway.md)
- [Gateway Adapters Reference](../reference/gateway-adapters.md)

