# Docker 打包

仓库在 `docker/` 下提供两个镜像定义，均需在**仓库根目录**执行 `docker build`。

| 镜像 | Dockerfile | 用途 |
|------|------------|------|
| Dashboard 运行时 | `docker/agent/Dockerfile` | 打包并运行 `dojoagents dashboard` |
| 文档站点 | `docker/docs-site/Dockerfile` | 构建 MkDocs 静态站并由 nginx 提供 |

## Dashboard 运行时镜像

### 构建阶段

`docker/agent/Dockerfile` 为多阶段构建：

1. **frontend**：在 Node 20 中 `npm ci` 并 `npm run build`，产出 `dojoagents/dashboard/web/dist/`。
2. **builder**：复制 Python 源码与预构建前端，打 wheel（构建前移除 `package.json`，避免 wheel 打包时再跑 npm）。
3. **runtime**：基于 `python:3.12-slim` 安装 wheel，默认启动 dashboard。

### 构建与运行

```bash
docker build -f docker/agent/Dockerfile -t dojoagents:latest .
```

```bash
docker run --rm -p 8765:8765 dojoagents:latest
```

浏览器访问 `http://127.0.0.1:8765`。

### 数据与配置

- 容器内配置与数据目录为 `/root/.dojo`（与本地默认 `~/.dojo` 一致）。
- 建议挂载 named volume 或 bind mount，以便保留 `agents.yaml`、缓存与会话数据。
- 模型 API Key 等敏感项通过配置文件或环境变量注入；不要将密钥 bake 进镜像。

### 常用覆盖

```bash
docker run --rm -p 8765:8765 \
  -v "$(pwd)/agents.yaml:/root/.dojo/agents.yaml:ro" \
  -e OPENAI_API_KEY="..." \
  dojoagents:latest
```

如需指定静态资源目录或强制重建前端（本地开发镜像时），可使用 `DOJO_DASHBOARD_STATIC_DIR`、`DOJO_DASHBOARD_REBUILD_FRONTEND` 等环境变量，行为与 [本地开发](local-development.md) 中 dashboard 启动一致。

## 文档站点镜像

### 构建阶段

`docker/docs-site/Dockerfile` 同样为多阶段：

1. **builder**：安装 MkDocs Material 与 i18n 插件，`mkdocs build --strict` 生成静态站。
2. **runtime**：将产物复制到 `nginx:1.27-alpine`，配置 `try_files` 以支持目录式 URL。

### 构建与运行

```bash
docker build -f docker/docs-site/Dockerfile -t dojoagents-docs:latest .
```

```bash
docker run --rm -p 8080:80 dojoagents-docs:latest
```

- 中文站点：`http://127.0.0.1:8080/`
- 英文站点：`http://127.0.0.1:8080/en/`

本地预览文档而不打镜像时，仍可使用：

```bash
uv run --extra docs mkdocs serve
```

## 与 Wheel 构建的关系

[构建发布](release-build.md) 中的 `uv build` / `python -m build` 会在宿主机上构建前端并打进 wheel。Docker agent 镜像则在镜像构建阶段完成前端编译，最终运行时镜像**不需要** Node.js。

两者目标不同：

- **wheel**：PyPI / 离线安装分发。
- **agent 镜像**：一键部署 dashboard 服务。
- **docs-site 镜像**：独立托管文档，不包含 agent 运行时。
