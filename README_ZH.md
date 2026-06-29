# DojoAgents

[**English**](README.md) · **中文说明**

**DojoAgents** 是一个面向量化金融的 Agent 运行时。它将 LLM 驱动的 Agent 循环、沙箱化工具、程序化技能（Skills）、记忆、定时任务、聊天网关、插件系统，以及 FastAPI/React Dashboard 整合为一套完整的本地分析工作流。

你可以用它运行市场研究 Agent、浏览多市场 Dashboard、管理投资组合，并通过 Slack、Telegram、微信等平台投递分析结果。

---

## 目录

- [功能概览](#功能概览)
- [系统架构](#系统架构)
- [Dashboard 视图与路由](#dashboard-视图与路由)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [安装方式](#安装方式)
- [配置说明](#配置说明)
- [CLI 命令参考](#cli-命令参考)
- [模块说明](#模块说明)
- [API 概览](#api-概览)
- [开发指南](#开发指南)
- [测试](#测试)
- [构建 Wheel 包](#构建-wheel-包)
- [文档索引](#文档索引)
- [许可证](#许可证)

---

## 功能概览

| 模块 | 能力 |
|------|------|
| **Agent 循环** | 多轮工具调用、SSE 流式输出、上下文压缩、护栏、任务 Harness |
| **LLM 提供商** | OpenAI 兼容端点、Gemini 原生、`dojoagents model` 交互式配置 |
| **金融数据** | Dojo SDK 工具：行情、K 线、板块、财务指标、新闻、外汇等 |
| **Dashboard** | 四大分析视图 — 组合分析、市场动态、板块发现、个股分析 — 及嵌入式 DojoAgent 面板 |
| **Agent 体验** | Run 模式对话（`/api/chat/runs`）、`dojo.v2` 类型化事件、内联可视化、Canvas 图表 |
| **Skills** | 内置与用户技能（`SKILL.md`）、懒加载、兼容 Claude Skills |
| **Tools** | 终端、代码执行、网页搜索/提取、MCP 服务、插件工具 |
| **Memory** | 可插拔记忆提供商；默认 skill-summary 将流程沉淀为技能 |
| **Scheduler** | APScheduler 定时任务，YAML 持久化 |
| **Gateway** | Slack、Telegram、Discord、飞书、企业微信、微信适配器，支持配对 |
| **Plugins** | 从 `~/.dojo/plugins` 发现原生与 Claude 格式插件 |
| **Multi-Agent** | 可选 Agent 池、委派工具、编排器与自动化钩子 |
| **Planning** | 可选计划驱动执行、状态存储与激活钩子 |

---

## 系统架构

CLI、Dashboard、Gateway、Scheduler 等所有入口，最终都汇聚到由 `ConfigStore` 构建的 **`Runtime`** 对象。Runtime 持有 Agent 循环、工具注册表、技能、记忆、扩展与任务存储。

```text
┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐
│ CLI chat    │  │ Dashboard    │  │ Gateway     │  │ Scheduler    │
└──────┬──────┘  └──────┬───────┘  └──────┬──────┘  └──────┬───────┘
       │                │                 │                │
       └────────────────┴────────┬────────┴────────────────┘
                                   ▼
                          ┌─────────────────┐
                          │ Runtime         │
                          │  ConfigStore    │
                          │  AgentLoop      │
                          │  ToolExecutor   │
                          │  SkillManager   │
                          │  MemoryManager  │
                          │  Extensions     │
                          └────────┬────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
        LLM Provider         Tool Registry         Dojo SDK / MCP
        (OpenAI / Gemini)    (沙箱化)              / Web / Terminal
```

**设计原则**

- **统一配置源** — 通过 `ConfigStore` 读写 `~/.dojo/agents.yaml`，禁止散落 YAML 解析逻辑。
- **结构化工具结果** — 所有工具经 `ToolExecutor` 返回 `{ok, content, error, metadata}`。
- **解耦投递层** — Gateway 与 Scheduler 不得绕过 `AgentLoop`。
- **金融逻辑在边缘** — 行情与 Dashboard 域逻辑放在 services/extensions，而非 Agent 循环内部。

完整设计文档见 [`docs/architecture.md`](docs/architecture.md)。

---

## Dashboard 视图与路由

React SPA 提供四个主 Tab，默认首页为 **组合分析（Portfolio）**。前端使用 Hash 路由：

| 路由 | Tab ID | 英文 | 中文 | 功能 |
|------|--------|------|------|------|
| `/` | `folio` | Portfolio | 组合分析 | 组合管理、净值曲线、基准对比、持仓、风险暴露、收益归因 |
| `#/market` | `market` | Markets | 市场动态 | 多市场列布局（美/港/A），板块涨跌榜，跨市场板块联动 |
| `#/sector` | `sector` | Sectors | 板块发现 | 行业 taxonomy（L1/L2/L3）、范围指标、绩效曲线、成分股 |
| `#/entity` | `entity` | Equities | 个股分析 | 单股深度分析 — K 线、PE 带、财务、新闻、事件、板块上下文 |

示例 URL（Dashboard 运行于 `http://127.0.0.1:8765`）：

```text
http://127.0.0.1:8765/              # 组合分析（默认首页）
http://127.0.0.1:8765/#/folio       # 组合分析
http://127.0.0.1:8765/#/market      # 市场动态
http://127.0.0.1:8765/#/sector      # 板块发现
http://127.0.0.1:8765/#/entity      # 个股分析
```

> **路由命名说明**：前端 Tab 与 Hash 路由已统一为 `folio` / `market` / `sector` / `entity`。旧路由 `#/mesh`、`#/sphere`、`#/core` 仍可访问，会自动重写为新地址。后端 REST API 路径仍保留历史命名（如 `/api/v1/dojo-mesh`），与前端路由相互独立。

**DojoAgent** 面板从右侧滑出，用于对话式分析。在「组合分析」Tab 下默认常驻；其他 Tab 需手动打开。Agent 对话采用 Run 模式 SSE，并设置 `metadata.event_format = "dojo.v2"` 以获取类型化工具/阶段事件。

流式协议、Canvas 沙箱与 API 细节见 [`docs/dashboard.md`](docs/dashboard.md)。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| **Python** | `>=3.11`，包名 `dojoagents` v0.0.1 |
| **Agent 核心** | `strands-agents`、OpenAI SDK、自定义 Provider |
| **API 服务** | FastAPI、uvicorn、APScheduler |
| **数据** | pandas、pyarrow、`dojosdk`、exchange-calendars |
| **集成** | MCP（`mcp`）、httpx、ddgs（网页搜索） |
| **前端** | React 19、TypeScript 5.8、Vite 8 |
| **测试** | pytest、pytest-asyncio |

---

## 快速开始

### 环境要求

- Python `>=3.11`
- Node.js `>=18` 与 npm `>=9`（前端开发或源码构建时需要）
- LLM API Key（如 `OPENAI_API_KEY`），或运行 `dojoagents model` 交互配置

### 安装并启动

```bash
cd DojoAgents

uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

cd dojoagents/dashboard/web
npm install
npm run build
cd ../../..

dojoagents model          # 可选：交互配置 LLM
dojoagents dashboard --host 127.0.0.1 --port 8765
```

浏览器打开 **http://127.0.0.1:8765/**，即可进入组合分析首页。

使用 Dojo SDK 行情数据时需设置：

```bash
export DOJO_API_KEY="your-key"
# 可选: export DOJO_BASE_URL="https://api.flowhale.ai"
```

---

## 安装方式

### 可编辑安装（开发）

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

### 仅运行时依赖

```bash
uv pip install -r requirements.txt
```

### 从预构建 Wheel 安装

已发布 Wheel 内已打包前端，**无需 Node.js**：

```bash
uv pip install dist/dojoagents-0.0.1-py3-none-any.whl
dojoagents dashboard
```

本地构建方法见 [构建 Wheel 包](#构建-wheel-包)。

---

## 配置说明

默认配置文件：**`~/.dojo/agents.yaml`**

`ConfigStore` 会将用户 YAML 与内置默认值深度合并，展开 `${ENV_VAR}` 占位符，对 API 暴露的配置做脱敏，并在文件变更时热重载。

最小示例：

```yaml
version: 1

llm_provider:
  default: openai
  providers:
    openai:
      model: gpt-4.1
      api_key_env: OPENAI_API_KEY

agent:
  max_iterations: 100
  max_tool_workers: 4
  default_skills: []

tools:
  sandbox:
    allowed_roots: ["${PWD}", "/tmp"]
    allow_network: false
    timeout_seconds: 120

memory:
  provider: skill_summary
  generated_skill_dir: "~/.dojo/skills/generated"

scheduler:
  enabled: true
  timezone: Asia/Shanghai
  store: "~/.dojo/agents/jobs.yaml"

gateway:
  enabled: true
  hooks: {}

dashboard:
  host: "127.0.0.1"
  port: 8765
  financial:
    dashboard_data_root: "~/.dojo/dashboard-data"

dojo_extensions:
  enabled:
    - dojo_research

dojosdk:
  cache_dir: "~/.cache/dojo"
```

**主要配置段**

| 配置段 | 用途 |
|--------|------|
| `llm_provider` | 提供商名称、模型、Base URL、API Key |
| `agent` | 迭代上限、默认技能、压缩、护栏 |
| `tools.sandbox` | 文件系统根目录、网络策略、命令白名单、超时 |
| `tools.web` | 网页搜索/提取后端与限制 |
| `memory` | 记忆提供商选择 |
| `skills` | 技能目录、禁用列表、Claude Skills 导入 |
| `scheduler` | 任务存储路径与时区 |
| `gateway.hooks` | 各聊天平台适配器凭证 |
| `dashboard.financial` | 本地数据缓存路径、刷新间隔 |
| `multi_agent` | Agent 池与委派（可选） |
| `planning` | 计划引擎（可选） |
| `mcp_servers` | MCP 服务连接 |
| `logging` | 日志级别与格式 |

LLM 交互配置：`dojoagents model`；Gateway 交互配置：`dojoagents gateway setup <adapter>`。Dashboard **设置**弹窗亦支持通过 `GET/PUT /api/config` 编辑脱敏后的配置。

---

## CLI 命令参考

控制台入口：**`dojoagents`**（`dojoagents.cli.main:main`）

| 命令 | 说明 |
|------|------|
| `dojoagents chat [message]` | 本地一次性或交互式 Agent 会话 |
| `dojoagents chat --market stock --symbols AAPL,MSFT --timeframe 1d "..."` | 附带量化上下文 |
| `dojoagents dashboard [--host HOST] [--port PORT]` | 启动 FastAPI + React Dashboard |
| `dojoagents gateway [--host HOST] [--port PORT]` | 启动聊天 Gateway 服务 |
| `dojoagents gateway setup all\|<adapter>` | 交互式配置 Gateway 适配器 |
| `dojoagents gateway pairing list\|approve\|deny` | 管理 DM 配对码 |
| `dojoagents model [--config PATH]` | 交互式 LLM 配置 |
| `dojoagents scheduler` | 加载并报告定时任务 |
| `dojoagents mcp serve` | 启动 MCP 服务桥接 |
| `dojoagents precompute-sector` | 预计算板块日度指标（见 `docs/precompute_sector_daily.md`） |

开发时无需全局安装：

```bash
uv run dojoagents dashboard --host 127.0.0.1 --port 8765
```

更多示例见 [`docs/usage.md`](docs/usage.md)。

---

## 模块说明

### Agent 运行时（`dojoagents/agent/`）

系统核心。**`Runtime.from_config_store()`** 组装依赖；**`AgentLoop.run()`** 执行回合生命周期：构建系统提示 → 预取记忆 → 调用 LLM → 经 `ToolExecutor` 调度工具 → 同步记忆并推送 SSE 事件。

| 文件 | 职责 |
|------|------|
| `runtime.py` | 从 `ConfigStore` 构建对象图 |
| `loop.py` | AgentLoop 编排与流式输出 |
| `models.py` | `ChatRequest`、OpenAI 兼容 Completion 类型 |
| `providers.py` / `gemini_provider.py` | LLM 提供商 |
| `harnesses/` | 任务完成度校验（如 `PortfolioTaskHarness`） |
| `events.py` | `dojo.v2` 类型化事件 |

### 配置（`dojoagents/config/`）

- `loader.py` — `ConfigStore`：加载、合并、环境变量展开、脱敏、保存
- `models.py` — 冻结 dataclass 配置 schema

读取用 `ConfigStore.snapshot()`；写入用 `raw()` + `_deep_merge()` + `save_raw()`。

### 工具与沙箱（`dojoagents/tools/`）

| 组件 | 说明 |
|------|------|
| `registry.py` / `executor.py` | 工具注册与异步执行 |
| `sandbox.py` | 文件系统、网络、命令策略 |
| `dojo_sdk_tool.py` | Dojo SDK 绑定（`dojo.sdk.stock.kline` 等） |
| `terminal_tool.py` / `code_execution_tool.py` | 终端与代码执行 |
| `web_searcher.py` | `web_search` + `web_extract` |
| `agent_viz.py` | `agent_viz_build` 内联图表块 |
| `mcp_tool.py` | MCP 工具发现 |
| `environments/` | 执行环境：local、Docker、SSH、Modal |

### 技能（`dojoagents/skills/`）

以 `SKILL.md`（YAML frontmatter + 指令）描述的程序化记忆。

| 内置技能 | 用途 |
|----------|------|
| `canvas-chart` | Dashboard Canvas 的 DOJO_CHART 协议 |
| `plan` / `writing-plans` | 计划编写 |
| `subagent-driven-development` | 多步子 Agent 工作流 |

### 记忆（`dojoagents/memory/`）

`MemoryProvider` 协议 + `MemoryManager`；默认 `SkillSummaryMemoryProvider` 将成功流程沉淀为生成技能。

### 定时任务（`dojoagents/cron/`）

`JobStore`（YAML 持久化）+ APScheduler 集成。

### Gateway（`dojoagents/gateway/`）

将 Slack、Telegram、Discord、飞书、企业微信、微信等平台消息规范化为 `ChatRequest`，并将 `AgentResponse` 发回。

```text
GET  /api/health
GET  /api/platforms
POST /api/webhook/{platform}
POST /api/send/{platform}/{target}
```

### 插件（`dojoagents/plugins/`）

从 `dojoagents/plugins/built_in/` 与 `~/.dojo/plugins` 发现；支持原生 `plugin.yaml` 与 Claude `.claude-plugin/plugin.json`。详见 [`docs/plugins.md`](docs/plugins.md)。

### Dojo 扩展（`dojoagents/dojo_extensions/`）

面向 Dojo 生态的域插件：健康检查、工具注册、Dashboard 卡片、Prompt 上下文注入。内置 **`dojo_research`**。

### 多 Agent 与计划（`multi_agent/`、`planning/`）

通过配置可选启用：Agent 池、委派、编排器、计划状态存储与执行引擎。详见 [`docs/multi_agent_plan_architecture.md`](docs/multi_agent_plan_architecture.md)。

### 量化上下文（`dojoagents/quant/`）

注入 Agent Prompt 与定时任务的 typed 市场边界（`market`、`symbols`、`timeframe` 等）。

### Dashboard 后端（`dojoagents/dashboard/`）

FastAPI 应用工厂 **`create_app(runtime)`**。

**域路由**（`/api/v1/...`）：

| 路由模块 | 对应前端视图 | 域 API 路径示例 |
|----------|--------------|-----------------|
| `dojo_folio.py` | 组合分析 `folio` | `/api/v1/dojo-folio/...` |
| `dojo_mesh.py` | 市场动态 `market` | `/api/v1/dojo-mesh/...` |
| `dojo_sphere.py` | 板块发现 `sector` | `/api/v1/dojo-sphere/...` |
| `dojo_core.py` | 个股分析 `entity` | `/api/v1/dojo-core/...` |

本地金融数据缓存目录：`dashboard.financial.dashboard_data_root`（默认 `~/.dojo/dashboard-data`）。

### Dashboard 前端（`dojoagents/dashboard/web/`）

React 19 + TypeScript + Vite。

| 目录 | 职责 |
|------|------|
| `src/views/` | `MarketView`、`SectorView`、`EntityView`、`FolioView`（路由：`folio`、`market`、`sector`、`entity`） |
| `src/components/Market/` | 市场动态视图组件 |
| `src/components/Sector/` | 板块发现视图组件 |
| `src/components/Entity/` | 个股分析视图组件 |
| `src/components/Folio/` | 组合分析视图组件 |
| `src/navigation/appTab.ts` | Hash 路由：`#/market`、`#/sector`、`#/entity`、`#/folio` |
| `src/types/`、`src/api/` | `market.ts`、`sector.ts`、`entity.ts`、`folio.ts` |
| `src/components/DojoAgent/` | Agent 面板、工具活动、可视化 |
| `src/i18n/` | 中英文文案 |
| `src/navigation/` | 跨视图上下文（Ticker、板块跳转） |

前端 HMR 开发：

```bash
# 终端 1 — 后端
dojoagents dashboard --host 127.0.0.1 --port 8765

# 终端 2 — Vite（/api 代理到后端）
cd dojoagents/dashboard/web && npm run dev
# 打开 http://localhost:5173
```

UI 规范见 [`docs/frontend-style-guide.md`](docs/frontend-style-guide.md)。

### CLI（`dojoagents/cli/`）

`main.py`（命令分发）、`gateway_setup.py`、`model_setup.py`、`mcp_serve.py`、`precompute_sector.py`。

---

## API 概览

### Dashboard 核心路由

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/config` | 脱敏配置 |
| `PUT` | `/api/config` | 部分合并并保存配置 |
| `GET` | `/api/jobs` | 定时任务列表 |
| `GET` | `/api/extensions` | 扩展健康状态 |
| `POST` | `/api/chat` | OpenAI 兼容对话 |
| `POST` | `/api/chat/runs` | 创建后台 Agent Run |
| `GET` | `/api/chat/runs/{run_id}/events` | SSE 事件流（支持 cursor） |
| `POST` | `/api/chat/runs/{run_id}/cancel` | 取消 Run |
| `GET` | `/` | React SPA |

金融域 API 挂载于 **`/api/v1/`**。Chat 扩展协议：设置 `metadata.event_format = "dojo.v2"`。详见 [`docs/dojo-chat-v2-protocol.md`](docs/dojo-chat-v2-protocol.md)。

---

## 开发指南

### 仓库结构

```text
.
├── dojoagents/           # Python 包
│   ├── agent/            # Agent 循环、Provider、Harness
│   ├── cli/              # 控制台入口
│   ├── config/           # ConfigStore 与类型 schema
│   ├── cron/             # 调度器与任务存储
│   ├── dashboard/        # FastAPI + React Web
│   ├── dojo_extensions/  # 域扩展协议
│   ├── gateway/          # 聊天平台适配器
│   ├── memory/           # 记忆提供商
│   ├── multi_agent/      # 多 Agent 池
│   ├── planning/         # 计划引擎
│   ├── plugins/          # 插件发现与钩子
│   ├── quant/            # QuantContext
│   ├── skills/           # 技能管理器与内置技能
│   └── tools/            # 工具注册、执行、沙箱
├── docs/                 # 架构与设计文档
├── tests/                # Pytest 测试
├── README.md             # 英文说明
├── README_ZH.md          # 中文说明（本文档）
└── AGENTS.md             # 贡献者 Agent 规范
```

贡献规范见 [`AGENTS.md`](AGENTS.md)。临时脚本请放在 **`.agents/scripts/`**。

---

## 测试

全量测试：

```bash
uv run --extra dev python -m pytest -q
```

定向测试：

```bash
uv run --extra dev python -m pytest tests/dashboard/routers -q
uv run --extra dev python -m pytest tests/test_dashboard_config_update.py -q
```

前端构建：

```bash
cd dojoagents/dashboard/web && npm run build
```

冒烟检查：

```bash
uv run --extra dev dojoagents --help
uv run --extra dev dojoagents dashboard --host 127.0.0.1 --port 8765
```

---

## 构建 Wheel 包

在仓库根目录（需要 Node.js 构建内嵌前端）：

```bash
uv build
```

构建流程会自动执行前端 `npm install && npm run build`，并将 `web/dist/` 打入 Wheel。

```bash
uv pip install dist/dojoagents-0.0.1-py3-none-any.whl
```

---

## 文档索引

| 文档 | 主题 |
|------|------|
| [`docs/architecture.md`](docs/architecture.md) | 系统架构与设计目标 |
| [`docs/usage.md`](docs/usage.md) | CLI、Gateway、Model 配置与开发流程 |
| [`docs/dashboard.md`](docs/dashboard.md) | Dashboard 协议、Canvas、SSE、API |
| [`docs/dojo-chat-v2-protocol.md`](docs/dojo-chat-v2-protocol.md) | `dojo.v2` 事件 schema |
| [`docs/plugins.md`](docs/plugins.md) | 插件系统与 Claude 兼容 |
| [`docs/dojo_sdk_integration.md`](docs/dojo_sdk_integration.md) | Dojo SDK 工具注册 |
| [`docs/multi_agent_plan_architecture.md`](docs/multi_agent_plan_architecture.md) | 多 Agent 与计划架构 |
| [`docs/frontend-style-guide.md`](docs/frontend-style-guide.md) | Dashboard UI 规范 |
| [`AGENTS.md`](AGENTS.md) | 贡献者 Agent 指令 |

---

## 许可证

DojoAgents 采用 [Apache License 2.0](LICENSE) 开源协议。
