# 配置

配置系统以 `dojoagents/config/loader.py::ConfigStore` 和 `dojoagents/config/models.py::AgentsConfig` 为准。默认配置文件是：

```text
~/.dojo/agents.yaml
```

运行时通过 `ConfigStore.snapshot()` 读取 typed config；Dashboard 配置 API 通过 `ConfigStore.raw()`、deep merge 和 `ConfigStore.save_raw()` 更新用户配置；对外展示必须使用 `ConfigStore.redacted()`。

## 示例

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
    # tavily / exa / firecrawl 等付费后端需要配置 api_key 或 api_key_env
    # api_key_env: TAVILY_API_KEY
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

## 字段分组

| 配置段 | 模型 | 用途 |
| --- | --- | --- |
| `llm_provider` | `LLMConfig` | 默认模型 provider 和 provider 列表 |
| `agent` | `AgentConfig` | Agent loop 限制、并发、guardrails、上下文压缩和默认技能 |
| `tools.sandbox` | `SandboxConfig` | terminal/code 工具允许的路径、命令、网络和超时 |
| `tools.web` | `WebToolsConfig` | Web search/extract 后端、大小限制和摘要阈值 |
| `memory` | `MemoryConfig` | memory provider 和生成技能目录 |
| `skills` | `SkillsConfig` | 用户 skill 目录、外部目录、禁用列表和 Claude skill 读取开关 |
| `scheduler` | `SchedulerConfig` | 计划任务开关、时区和 job store |
| `gateway` | `GatewayConfig` | chat gateway 开关和平台 hook 配置 |
| `dashboard` | `DashboardConfig` | Dashboard 监听地址、profiler 和金融数据配置 |
| `dojo_extensions` | `DojoExtensionsConfig` | 第一类 Dojo extension 列表 |
| `logging` | `LoggingConfig` | 日志级别、格式和时间格式 |
| `mcp_servers` | `dict` | MCP server 配置 |
| `dojosdk` | `DojoSDKConfig` | DojoSDK base URL、API key、timeout 和重试 |
| `multi_agent` | `MultiAgentConfig` | 多智能体开关、worker 数和默认 agent 定义 |
| `planning` | `PlanConfig` | plan 工具开关、自动规划阈值、plan store 和最大 step |
| `sessions` | `SessionsConfig` | runtime session 存储、恢复、memory 同步和导出目录 |

## 敏感字段

API key 可以通过两种方式配置：

- `api_key_env`：推荐方式，从环境变量读取。
- `api_key`：直接写入配置文件，仅适合本地私有环境。

Dashboard 和 API 对外展示配置时必须使用 `ConfigStore.redacted()`。不要把 provider key、DojoSDK key 或 gateway token 原样返回给前端。

## 更新规则

- 新代码读取 typed config：`ConfigStore.snapshot()`。
- 用户配置更新：`ConfigStore.raw()` + `_deep_merge()` + `ConfigStore.save_raw()`。
- 新增配置字段时，需要同时更新：
  - `dojoagents/config/models.py`
  - `dojoagents/config/loader.py::_to_config()`
  - 相关测试
  - 本页中英文文档

不要新增第二套 YAML parser、环境变量展开层、配置 singleton 或默认配置路径。

## 相关代码

- `dojoagents/config/models.py`
- `dojoagents/config/loader.py`
- `dojoagents/dashboard/server.py`
- `tests/test_config_multi_agent_plan.py`
- `tests/test_core_contracts.py`
