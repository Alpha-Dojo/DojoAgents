# 添加 Dashboard 路由

## 标准路径

新增 Dashboard API 时按以下分层：

| 内容 | 位置 |
| --- | --- |
| Router | `dojoagents/dashboard/routers/` |
| Request/response schema | `dojoagents/dashboard/schemas/` |
| Business logic | `dojoagents/dashboard/services/` |
| Dependency access | `dojoagents/dashboard/deps.py` |
| App include | `dojoagents/dashboard/server.py` |

## 错误处理

- 预期 HTTP 失败使用 `fastapi.HTTPException`。
- 或按现有路由风格返回 `JSONResponse(status_code=..., content={"error": ...})`。
- 边界层记录异常，不要静默吞掉 broad exception。

## 存储

JSON/JSONL 存储优先使用：

- `AtomicJsonStore`
- `AtomicJsonlStore`

不要对用户控制 key 做不安全路径拼接。

