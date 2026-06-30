# 模型配置

## 适用场景

DojoAgents 通过统一配置文件读取 LLM provider、模型、API key、base URL 等参数。默认配置路径是：

```text
~/.dojo/agents.yaml
```

## 交互式配置

推荐使用 CLI 生成配置：

```bash
dojoagents model
```

使用自定义配置文件：

```bash
dojoagents model --config ./agents.yaml
```

交互流程会引导你选择 provider、输入 base URL、输入 API key、探测模型列表，并将配置写入 YAML。

## 配置原则

- 运行时代码读取配置时应通过 `ConfigStore.snapshot()`。
- Dashboard 暴露配置时必须使用 redacted config，避免泄露密钥。
- 可以在 YAML 中使用环境变量占位，例如 `${OPENAI_API_KEY}`。

## 下一步

完成模型配置后，阅读 [第一次 Agent 运行](first-agent-run.md)。

