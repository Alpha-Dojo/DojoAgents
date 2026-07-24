# 添加工具

## 标准路径（通用工具）

1. 在 `dojoagents/tools/` 中实现工具模块。
2. 定义一个或多个 `ToolSpec`。
3. handler 必须是 async，并返回 `dict[str, Any]` 或字符串。
4. 在 `Runtime.from_config_store()` 或插件 registry 中注册。
5. 添加 focused tests。

## 金融只读工具（优先）

新的行情 / 板块 / 预计算 / 新闻只读能力：

1. 优先在 `dojoagents/tools/dojo_sdk_tool.py` 增加 `OFFLINE_TOOL_BINDINGS`（或同层 SDK 封装模块）。
2. 保证 handler 支持 **可过滤查询**（date / market / L1–L3 / ticker），避免整表 dump。
3. 在 `tests/test_dojo_sdk_tool.py`（或并列测试）覆盖注册与调用。
4. 更新 [DojoSDK](../reference/dojo-sdk.md) 清单。

**不要**把新的 Agent 金融只读依赖加到 `dashboard/tools/domain_tools.py`。

## Dashboard 工具（受限）

| 类型 | 路径 | 何时使用 |
| --- | --- | --- |
| Portfolio 写工具 | `dashboard/tools/portfolio_tools.py` | 组合创建/调仓等有副作用写路径（暂留） |
| Domain 读工具 | `dashboard/tools/domain_tools.py` | **Legacy**；仅维护既有行为，新 Task 勿新增 |

注册：`register_dashboard_domain_tools` / `register_dashboard_portfolio_tools`（`dashboard/server.py`、tasks CLI）。

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
