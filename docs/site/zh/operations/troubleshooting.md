# 排错

## Dashboard 无法打开

检查前端是否已经构建：

```bash
cd dojoagents/dashboard/web
npm run build
```

检查后端是否启动：

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

## 模型请求失败

检查：

- `~/.dojo/agents.yaml` 中的 provider、base URL、model。
- API key 是否通过环境变量或 YAML 正确提供。
- 是否能通过 `dojoagents model` 重新探测模型列表。

## Gateway 收不到消息

检查：

- adapter 是否启用。
- webhook URL 是否可达。
- `gateway.hooks.<adapter>` 配置是否完整。
- 是否需要批准 pairing code。

## SSE 中断

检查：

- 前端是否正确使用 `stream=true`。
- 代理或浏览器是否缓冲 SSE。
- 后端日志中是否有 provider 或 tool error。

## DojoSDK 数据问题

检查：

- 本地 `../DojoSDK` source 是否存在。
- 相关 store 是否加载成功。
- 预计算数据是否需要重新生成。

