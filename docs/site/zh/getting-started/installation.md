# 安装

## 适用场景

本页用于本地开发或从源码运行 DojoAgents。仓库要求 Python `>=3.11`；Dashboard 前端需要 Node.js `>=18` 和 npm `>=9`。

## 从源码安装

从仓库根目录执行：

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

如果只需要运行时依赖，不安装本地包：

```bash
uv pip install -r requirements.txt
```

## 构建 Dashboard 前端

Dashboard 后端会服务 `dojoagents/dashboard/web/dist/` 的构建产物。从仓库根目录执行：

```bash
cd dojoagents/dashboard/web
npm install
npm run build
```

## 验证安装

回到仓库根目录后运行：

```bash
dojoagents --help
```

开发环境中也可以直接使用：

```bash
uv run --extra dev dojoagents --help
```

## 下一步

继续阅读 [启动 Dashboard](quickstart-dashboard.md)。

