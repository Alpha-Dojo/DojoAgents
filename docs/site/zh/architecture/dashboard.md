# Dashboard 架构

## 目标

Dashboard 把 FastAPI 后端、React 前端、金融数据服务和 Agent chat API 组合成一个本地分析界面。

## 后端分层

| 层 | 目录 | 说明 |
| --- | --- | --- |
| App factory | `dojoagents/dashboard/server.py` | 创建 FastAPI app、注册路由和生命周期 |
| Dependencies | `dojoagents/dashboard/deps.py` | 获取 runtime、store、domain services |
| Routers | `dojoagents/dashboard/routers/` | HTTP 路由 |
| Schemas | `dojoagents/dashboard/schemas/` | Pydantic request/response |
| Services | `dojoagents/dashboard/services/` | 金融、store、cache、gateway 逻辑 |
| Static/Web | `dojoagents/dashboard/static/`, `dojoagents/dashboard/web/` | Canvas 模板与 React SPA |

## 通信

- `POST /api/chat` 提供 OpenAI-compatible chat。
- 流式响应使用 SSE。
- `dojo.v2` 事件通过 OpenAI chunk 的 `dojo_event` 字段扩展。
- REST 路由使用 `/api/v1` 下的 domain routers。

## 深入阅读

- [Dashboard API](../reference/dashboard-api.md)
- 后续补充：将 Dashboard 旧设计中仍有效的细节继续收敛到本页
