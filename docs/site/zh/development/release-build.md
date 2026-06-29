# 构建发布

## Wheel 构建

从仓库根目录执行：

```bash
uv build
```

或使用标准 Python build frontend：

```bash
python -m pip install build
python -m build
```

构建过程会：

1. 在 `dojoagents/dashboard/web` 下运行 `npm install && npm run build`。
2. 成功后移除 `node_modules`。
3. 将 `web/dist/` 打包进 wheel。

## 安装 Wheel

```bash
uv pip install dist/dojoagents-0.0.1-py3-none-any.whl
```

预构建 wheel 用户不需要 Node.js。

