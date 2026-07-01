# 架构总览

## 目标

DojoAgents 的核心目标是把 LLM Agent、量化金融数据、工具执行、Dashboard、Gateway、插件和计划任务整合为一个可本地运行、可扩展的分析 runtime。

## 模块地图

```text
dojoagents/
├── agent/            # Agent loop, providers, runtime, events, guardrails
├── cli/              # dojoagents console entry point
├── config/           # ConfigStore and frozen dataclass schema
├── cron/             # Scheduled jobs
├── dashboard/        # FastAPI backend, services, routers, React app
├── gateway/          # Chat platform gateway and adapters
├── memory/           # Memory providers and manager
├── multi_agent/      # Agent pool and delegation
├── planning/         # Plan models, execution, triggers
├── plugins/          # Plugin discovery and hooks
├── quant/            # Quant context and workflow primitives
├── skills/           # Skill loader/cache/manager
├── tools/            # ToolSpec registry, executor, sandbox, concrete tools
└── utils/            # Event bus and shared utilities
```

## 核心流程

1. CLI、Dashboard 或 Gateway 构造请求。
2. `Runtime` 从 `ConfigStore` 读取配置并组装 provider、tools、skills、memory、scheduler。
3. `AgentLoop` 调用 LLM provider。
4. 如果模型请求工具，`ToolExecutor` 经过 sandbox policy 后执行 `ToolSpec.handler`。
5. 工具结果被规范化为 `ToolResult`，再进入 Agent history、事件流和 Dashboard UI。
6. Dashboard 通过 OpenAI-compatible response 或 SSE `dojo_event` 将结果返回前端。

## 关键边界

- 配置统一从 `dojoagents/config/loader.py::ConfigStore` 读取和保存。
- 日志统一使用 `dojoagents.logging.LOGGER` 或 `get_logger()`。
- 工具统一通过 `ToolRegistry`、`ToolSpec`、`ToolExecutor` 注册和执行。
- Dashboard 新能力按 routers、schemas、services、deps 分层。
- 插件从内置目录和 `~/.dojo/plugins` 发现。

## 深入阅读

- [Runtime](runtime.md)
- [Agent Loop](agent-loop.md)
- [Tools 与 Sandbox](tools-and-sandbox.md)
- [Dashboard](dashboard.md)
- [Gateway](gateway.md)
