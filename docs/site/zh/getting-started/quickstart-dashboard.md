# 启动 Dashboard

## 适用场景

Dashboard 是 DojoAgents 的本地 Web UI，包含 React SPA、OpenAI-compatible chat API、SSE 流式响应和金融分析页面。

## 启动后端

确保已经完成 [安装](installation.md) 和前端构建，然后从仓库根目录执行：

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

打开：

```text
http://127.0.0.1:8765/
```

开发时也可以直接运行 CLI 文件：

```bash
uv run dojoagents/cli/main.py dashboard --host 127.0.0.1 --port 8765
```

## 前端热更新

先启动 Dashboard 后端：

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

另开一个终端运行 Vite：

```bash
cd dojoagents/dashboard/web
npm run dev
```

前端开发服务器默认在：

```text
http://localhost:5173/
```

## 使用 Mock 数据

```bash
cd dojoagents/dashboard/web
VITE_USE_MOCKS=true npm run dev
```

如果希望后端服务 mock 构建产物：

```bash
cd dojoagents/dashboard/web
VITE_USE_MOCKS=true npm run build
cd ../../..
dojoagents dashboard --host 127.0.0.1 --port 8765
```

## 下一步

继续阅读 [模型配置](model-configuration.md) 和 [Dashboard 用户指南](../user-guide/dashboard.md)。

