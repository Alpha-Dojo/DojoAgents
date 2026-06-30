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

## Rules

- Runtime code should read typed config through `ConfigStore.snapshot()`.
- Dashboard/API exposure must use redacted config.
- YAML may reference environment variables such as `${OPENAI_API_KEY}`.

