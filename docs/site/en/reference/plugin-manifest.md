# Plugin Manifest

Plugin discovery and loading are implemented in `dojoagents/plugins/registry.py`.

## Supported Files

A plugin directory may contain:

- `plugin.yaml`
- `.claude-plugin/plugin.json`
- `plugin.json`
- `hooks.json`
- `hooks/hooks.json`
- `__init__.py`

User plugins are discovered from `~/.dojo/plugins`. Built-in plugins live under `dojoagents/plugins/built_in/`.

## Manifest Fields

| Field | Purpose |
| --- | --- |
| `name` | Plugin name |
| `version` | Version, default `0.2.0` |
| `description` | Human-readable description |
| `provides_tools` | Tool names exposed by the plugin |
| `provides_hooks` | Hook names exposed by the plugin |

Runtime manifests also track `path`, `source`, and `is_claude`.

## Valid Hooks

- `on_session_start`
- `pre_llm_call`
- `pre_api_request`
- `post_api_request`
- `pre_tool_call`
- `post_tool_call`
- `transform_tool_result`
- `transform_llm_output`
- `post_llm_call`
- `on_session_end`

Claude-style hooks are mapped through `CLAUDE_TO_DOJO_HOOKS`; unsupported hook names are logged but should not be used for new plugins.

## Plugin Capabilities

Plugins may register:

- hooks through `DojoPluginContext.register_hook()`;
- tools through `DojoPluginContext.register_tool()`;
- skill directories;
- MCP server configs;
- default multi-agent configs.

## Optional Adanos Research Plugin

The bundled `adanos` plugin exposes `adanos_sentiment` only when the process
environment contains `ADANOS_API_KEY`. Set it in your shell or secret manager
before starting DojoAgents, then restart after changing or removing it. The key
is never a tool argument and no default configuration changes are required.

[Adanos](https://adanos.org/) is a commercial API with a free plan. Access,
history and quotas depend on the account plan; HTTP 401/403/429 errors remain
errors rather than neutral sentiment. See the [API documentation](https://api.adanos.org/docs).

Sources are `reddit_stocks`, `reddit_crypto`, `x_stocks`, `news_stocks` and
`polymarket_stocks`. Operations are `asset`, `trending`, `market` and `compare`.
For example:

```json
{"source":"news_stocks","operation":"asset","asset":"BRK","from":"2026-10-01","to":"2026-10-02"}
```

Use `assets: ["BTC", "ETH"]` for crypto comparisons. News identifiers are
company keys, not share-class symbols: use `BRK`, not `BRK.B`. `from` and `to`
are inclusive UTC dates; `days` is not supported. The provider response is
returned with its source, URL and requested dates, without score remapping.
Treat it as additional research evidence, not a price feed, point-in-time
backtest dataset or independent buy/sell signal. Only Reddit supports crypto.

## Code Anchors

- `dojoagents/plugins/registry.py`
- `dojoagents/plugins/__init__.py`
- `dojoagents/tools/plugin_manage.py`
