# 本地开发

## 环境

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Dashboard 前端

```bash
cd dojoagents/dashboard/web
npm install
npm run dev
```

后端：

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

## 文档站

安装 docs extra 后可运行：

```bash
uv run --extra docs mkdocs serve
```

构建：

```bash
uv run --extra docs mkdocs build --strict
```

## 临时脚本

仓库规则要求临时脚本放在：

```text
.agents/scripts/
```

