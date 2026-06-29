# 添加工具

## 标准路径

1. 在 `dojoagents/tools/` 中实现工具模块。
2. 定义一个或多个 `ToolSpec`。
3. handler 必须是 async，并返回 `dict[str, Any]` 或字符串。
4. 在 `Runtime.from_config_store()` 或插件 registry 中注册。
5. 添加 focused tests。

## ToolSpec 示例

```python
ToolSpec(
    name="example_tool",
    description="Short model-facing description.",
    parameters={"type": "object", "properties": {}},
    handler=handle_example_tool,
)
```

## 注意事项

- 不要绕过 `ToolExecutor`。
- 不要返回任意结果形态；让 executor 规范化。
- 有副作用的工具应返回 `resource_changes`。
- 可视化结果应返回 `viz_blocks`。
- 阻塞 I/O 应放到 async client 或 bounded executor 中。

