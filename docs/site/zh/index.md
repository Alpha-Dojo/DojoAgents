# DojoAgents

DojoAgents 是一个面向量化金融分析工作流的 Agent Runtime。它把 LLM-driven agent loop、工具执行、技能、记忆、计划任务、插件、聊天网关和 FastAPI/React Dashboard 组合成一个本地可运行的分析系统。

## 从哪里开始

- 新用户先读 [安装](getting-started/installation.md) 和 [启动 Dashboard](getting-started/quickstart-dashboard.md)。
- 想接入模型，读 [模型配置](getting-started/model-configuration.md)。
- 想调用后端接口，读 [Chat API](reference/chat-api.md) 和 [dojo.v2 协议](reference/dojo-v2-protocol.md)。
- 想扩展系统，读 [仓库地图](development/repository-map.md)、[添加工具](development/adding-tools.md) 和 [测试](development/testing.md)。
- 想理解整体架构，读 [架构总览](architecture/overview.md)。

## 核心能力

| 能力 | 入口 |
| --- | --- |
| Agent runtime | [Runtime 架构](architecture/runtime.md) |
| Dashboard | [Dashboard 用户指南](user-guide/dashboard.md) |
| OpenAI-compatible chat | [Chat API](reference/chat-api.md) |
| Tools and sandbox | [Tools 与 Sandbox](architecture/tools-and-sandbox.md) |
| Skills | [Skills 用户指南](user-guide/skills.md) |
| Gateway | [Gateway 用户指南](user-guide/gateway.md) |
| Plugins | [Plugins 架构](architecture/plugins.md) |
| Multi-agent and planning | [Multi-Agent 与 Planning](architecture/multi-agent-planning.md) |

## 文档状态

这套 MkDocs 文档采用“正式站点内容 + 设计记录分层”的结构。主导航中的指南和 reference 以当前仓库实现为准；旧的规划、迁移和原型材料保留在 [设计记录](design-notes/index.md)，用于理解演进背景。

## 快速命令

从仓库根目录安装开发依赖：

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

构建 Dashboard 前端：

```bash
cd dojoagents/dashboard/web
npm install
npm run build
```

启动 Dashboard：

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

