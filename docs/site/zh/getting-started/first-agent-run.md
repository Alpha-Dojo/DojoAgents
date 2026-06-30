# 第一次 Agent 运行

## CLI 运行

从仓库根目录执行：

```bash
dojoagents chat "Analyze BTC market structure" --market crypto --symbols BTC-USD --timeframe 1d
```

如果不传 message，CLI 会提示输入：

```bash
dojoagents chat
```

## Dashboard 运行

1. 启动 Dashboard。
2. 打开 `http://127.0.0.1:8765/`。
3. 在聊天输入框中输入分析任务。
4. 观察 Agent 消息、工具活动、可视化区块和最终回答。

## API 运行

```bash
curl -N http://127.0.0.1:8765/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "messages": [{"role": "user", "content": "帮我总结今天的市场结构"}],
    "stream": true,
    "metadata": {"session_id": "quickstart", "event_format": "dojo.v2"}
  }'
```

更多字段见 [Chat API](../reference/chat-api.md) 和 [dojo.v2 协议](../reference/dojo-v2-protocol.md)。

