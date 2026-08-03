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

## 配置自定义 OpenAI 兼容模型

该模型通过 OpenAI 兼容接口接入。推荐在 `~/.dojo/agents.yaml` 中使用独立的 provider 名称，并通过环境变量提供 API key：

```yaml
version: 1

llm_provider:
  default: custom-openai
  providers:
    custom-openai:
      model: your-model-name
      base_url: https://api.example.com/v1
      api_key_env: CUSTOM_OPENAI_API_KEY
      context_window: 128000
      max_tokens: 8192

agent:
  model: your-model-name
```

启动 DojoAgents 前设置密钥：

```bash
export CUSTOM_OPENAI_API_KEY="<your-api-key>"
```

这里的 `custom-openai` 是本地 provider ID，可自行命名，但必须与 `llm_provider.default` 一致；`your-model-name` 会原样发送给服务端，应保留提供方要求的大小写。如果 `base_url` 已包含 `/v1`，不要再追加 `/chat/completions`，OpenAI SDK 会自动拼接请求路径。

也可以运行 `dojoagents model`，选择 `Custom Endpoint`，依次填写：

- Custom provider name：`custom-openai`
- Base URL：`https://api.example.com/v1`
- Model name：`your-model-name`

如果网关不支持 `/models` 探测，CLI 会提示手动输入模型名。CLI 默认会把输入的 API key 写入 YAML；如需避免明文保存，配置完成后删除 `api_key`，改用上例的 `api_key_env`。

## 配置原则

- 运行时代码读取配置时应通过 `ConfigStore.snapshot()`。
- Dashboard 暴露配置时必须使用 redacted config，避免泄露密钥。
- 可以在 YAML 中使用环境变量占位，例如 `${OPENAI_API_KEY}`。

## 下一步

完成模型配置后，阅读 [第一次 Agent 运行](first-agent-run.md)。
