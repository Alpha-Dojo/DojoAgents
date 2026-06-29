# Dashboard API

## 状态

Dashboard API 由 `dojoagents/dashboard/server.py` 注册。核心 chat 入口是 `POST /api/chat`，domain API 通过 router 模块挂载。

## 基础入口

| Method | Path | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/config` | 脱敏配置 |
| `GET` | `/api/jobs` | Scheduled jobs |
| `GET` | `/api/extensions` | Extension 列表 |
| `POST` | `/api/chat` | Chat completions |

## Domain Routers

当前 router 模块包括：

- `dojo_core`
- `dojo_folio`
- `dojo_mesh`
- `dojo_sphere`
- `market`
- `markets`
- `portfolio`
- `sector`
- `sectors`
- `ticker`
- `utility`

具体 path 以各 router 文件中的定义为准。

## 错误处理

预期 HTTP 失败使用 `fastapi.HTTPException` 或现有路由中一致的 `JSONResponse(status_code=..., content={"error": ...})` 模式。

