# DojoSDK

## 状态

DojoAgents 通过 `dojosdk` 依赖和 `dojoagents/tools/dojo_sdk_tool.py` 暴露金融数据工具能力。Dashboard 服务层也会通过 domain services 与 Dojo 数据网关交互。

## 相关配置

DojoSDK 依赖由 `pyproject.toml` 管理。当前项目使用本地 source 覆盖：

```toml
[tool.uv.sources]
dojosdk = { path = "../DojoSDK" }
```

## 错误边界

Dashboard 的 Dojo data gateway error family 位于 `dojoagents/dashboard/services/dojo_data_gateway.py`，包括：

- `GatewayError`
- `GatewayBadResponseError`
- `GatewayTimeoutError`
- `GatewayUnavailableError`
- `GatewayResult`

## 深入阅读

旧版集成说明的核心内容已并入本页；迁移背景可在 `docs/plans/` 中查找。
