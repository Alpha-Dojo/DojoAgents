# Configuration

Configuration is based on `dojoagents/config/loader.py::ConfigStore` and `dojoagents/config/models.py::AgentsConfig`. The default file is:

```text
~/.dojo/agents.yaml
```

Runtime code reads typed config through `ConfigStore.snapshot()`. The dashboard config API updates user config through `ConfigStore.raw()`, deep merge, and `ConfigStore.save_raw()`. External exposure must use `ConfigStore.redacted()`.

## Example

```yaml
version: 1

llm_provider:
  default: openai
  providers:
    openai:
      author: openai
      model: gpt-4.1
      base_url: https://api.openai.com/v1
      api_key_env: OPENAI_API_KEY
      context_window: 128000

agent:
  max_iterations: 100
  max_tool_workers: 4
  lazy_skills: true
  enable_skill_cache: true
  enable_guardrails: true
  enable_think_scrubbing: true
  enable_context_compression: true
  compression_threshold_ratio: 0.8
  default_context_window: 32768
  default_skills:
    - dojo-quant-analyst

tools:
  sandbox:
    allowed_roots:
      - ${PWD}
      - /tmp
    allow_network: false
    allowed_commands: []
    timeout_seconds: 120
  web:
    search_backend: ddgs
    extract_backend: fetch
    max_extract_urls: 5
    max_content_bytes: 2000000

skills:
  dir: ~/.dojo/skills
  generated_skill_dir: ~/.dojo/skills/generated
  external_dirs: []
  disabled: []
  read_claude_skills: false

dashboard:
  host: 127.0.0.1
  port: 8765
  profiler:
    enabled: false
  financial:
    dashboard_data_root: ~/.dojo/dashboard-data
    sdk_cache_dir: ~/.cache/huggingface/hub
    stock_quote_refresh_seconds: 15
    constituent_kline_max_concurrent: 8

gateway:
  enabled: true
  hooks: {}

sessions:
  enabled: true
  provider: dojo_repository
  root: ~/.dojo/agents/strands_sessions
  agent_id: dojo-agent
  persist_openai_history: true
  sync_memory: true
  export_default_dir: ~/Desktop/dojo-chat-export
```

## Sections

| Section | Model | Purpose |
| --- | --- | --- |
| `llm_provider` | `LLMConfig` | Default model provider and provider definitions |
| `agent` | `AgentConfig` | Agent loop limits, concurrency, guardrails, context compression, default skills |
| `tools.sandbox` | `SandboxConfig` | Allowed paths, commands, networking, and timeout for terminal/code tools |
| `tools.web` | `WebToolsConfig` | Web search/extract backend and size/summary limits |
| `memory` | `MemoryConfig` | Memory provider and generated skill directory |
| `skills` | `SkillsConfig` | User skill directories, external dirs, disabled skills, Claude skill import |
| `scheduler` | `SchedulerConfig` | Scheduled job switch, timezone, and job store |
| `gateway` | `GatewayConfig` | Chat gateway switch and platform hook configuration |
| `dashboard` | `DashboardConfig` | Dashboard host/port, profiler, and financial data settings |
| `dojo_extensions` | `DojoExtensionsConfig` | First-class Dojo extension list |
| `logging` | `LoggingConfig` | Log level, format, and date format |
| `mcp_servers` | `dict` | MCP server configuration |
| `dojosdk` | `DojoSDKConfig` | DojoSDK base URL, API key, timeout, retries |
| `multi_agent` | `MultiAgentConfig` | Multi-agent switch, worker count, default agents |
| `planning` | `PlanConfig` | Planning tools, auto-plan threshold, plan store, max steps |
| `sessions` | `SessionsConfig` | Runtime session storage, restore, memory sync, export directory |

## Secrets

API keys can be configured in two ways:

- `api_key_env`: recommended; reads from an environment variable.
- `api_key`: direct config file value; only suitable for local private environments.

Dashboard and API responses must expose config through `ConfigStore.redacted()`. Provider keys, DojoSDK keys, and gateway tokens must not be returned to the frontend in plaintext.

## Update Rules

- Typed runtime reads: `ConfigStore.snapshot()`.
- User updates: `ConfigStore.raw()` + `_deep_merge()` + `ConfigStore.save_raw()`.
- New config fields must update:
  - `dojoagents/config/models.py`
  - `dojoagents/config/loader.py::_to_config()`
  - focused tests
  - this page in both languages

Do not add a second YAML parser, environment expansion layer, config singleton, or default config path.

## Code Anchors

- `dojoagents/config/models.py`
- `dojoagents/config/loader.py`
- `dojoagents/dashboard/server.py`
- `tests/test_config_multi_agent_plan.py`
- `tests/test_core_contracts.py`
