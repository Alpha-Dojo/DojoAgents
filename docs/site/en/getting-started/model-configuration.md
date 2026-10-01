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

Probed models are saved as the provider's `models` candidates, while the
selected model remains its `model` default. The Dashboard exposes the current
configured choices through `GET /api/v1/models`.

## Rules

- Runtime code should read typed config through `ConfigStore.snapshot()`.
- Dashboard/API exposure must use redacted config.
- YAML may reference environment variables such as `${OPENAI_API_KEY}`.
- A provider can add request headers with an `extra_headers` string mapping;
  environment placeholders are supported in header values.

## LiteLLM

The `litellm` provider reaches every backend [LiteLLM](https://github.com/BerriAI/litellm)
supports (Anthropic, Bedrock, Vertex AI, Azure OpenAI, Gemini, Mistral, Ollama,
and more) through one provider, in-process via the LiteLLM SDK. Install the
optional extra first:

```bash
pip install "dojoagents[litellm]"
```

The model name carries the route, and each route reads
its provider's usual credentials (`ANTHROPIC_API_KEY`, `AWS_*`,
`GOOGLE_APPLICATION_CREDENTIALS`, ...), so `api_key` is optional.

```yaml
llm_provider:
  default: litellm
  providers:
    litellm:
      model: anthropic/claude-sonnet-4-5
      models:
        - anthropic/claude-sonnet-4-5
        - bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0
        - vertex_ai/gemini-2.5-pro
```

Routes that need an endpoint (`azure/...`, `ollama/...`, `hosted_vllm/...`) take
it from `base_url`.

Context windows and image support for known models come from LiteLLM's model
map, so compression thresholds and the Dashboard's image-input check follow the
selected model; `context_window` still overrides.
