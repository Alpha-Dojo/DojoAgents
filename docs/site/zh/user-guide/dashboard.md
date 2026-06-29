# Dashboard

## 适用场景

Dashboard 提供本地 Web UI，用于与 Agent 对话、查看工具执行过程、浏览金融数据和使用可视化结果。

## 启动

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

打开：

```text
http://127.0.0.1:8765/
```

## API 入口

| Method | Path | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/config` | 脱敏配置 |
| `GET` | `/api/jobs` | 计划任务 |
| `GET` | `/api/extensions` | 已注册扩展 |
| `POST` | `/api/chat` | OpenAI-compatible chat |
| `GET` | `/` | React SPA |

## 前端开发

```bash
cd dojoagents/dashboard/web
npm run dev
```

Vite 默认代理后端 `http://127.0.0.1:8765/api`。

## 深入阅读

- [Dashboard 架构](../architecture/dashboard.md)
- [Dashboard API Reference](../reference/dashboard-api.md)
- 后续补充：将 Dashboard 旧设计中的仍有效细节继续收敛到当前用户指南、架构和 API 页面
