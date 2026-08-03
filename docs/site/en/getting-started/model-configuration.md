# Model Configuration

DojoAgents reads LLM provider configuration from:

```text
~/.dojo/agents.yaml
```

## Interactive Setup

```bash
dojoagents model
```

Custom config file:

```bash
dojoagents model --config ./agents.yaml
```

The command lets you choose a provider, set a base URL, enter an API key, probe available models, and save the result.

## Configure a custom OpenAI-compatible provider

This model is exposed through an OpenAI-compatible endpoint. Add a dedicated provider to `~/.dojo/agents.yaml` and supply the API key through an environment variable:

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

Set the key before starting DojoAgents:

```bash
export CUSTOM_OPENAI_API_KEY="<your-api-key>"
```

`custom-openai` is a local provider ID. It can be renamed, but it must match `llm_provider.default`. `your-model-name` is sent to the endpoint as written, so preserve the casing required by the provider. When a base URL already includes `/v1`, do not append `/chat/completions`; the OpenAI SDK adds that request path.

You can also run `dojoagents model`, select `Custom Endpoint`, and enter:

- Custom provider name: `custom-openai`
- Base URL: `https://api.example.com/v1`
- Model name: `your-model-name`

If the gateway does not support `/models`, the CLI falls back to manual model entry. The CLI stores an entered API key in YAML by default. To avoid storing it in plain text, remove `api_key` after setup and use `api_key_env` as shown above.

## Rules

- Runtime code should read typed config through `ConfigStore.snapshot()`.
- Dashboard/API exposure must use redacted config.
- YAML may reference environment variables such as `${OPENAI_API_KEY}`.
