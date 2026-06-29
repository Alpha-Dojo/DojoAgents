# Runtime

## 目标

Runtime 是 DojoAgents 的对象图组装层。它从配置构造 Agent、provider、tools、skills、memory、scheduler、plugins 和 dashboard 依赖。

## 入口

| 入口 | 用途 |
| --- | --- |
| `Runtime.from_default_config()` | 使用默认 `~/.dojo/agents.yaml` |
| `Runtime.from_config_store(ConfigStore(...))` | 使用指定配置源 |

## 依赖边界

Runtime 不应重复实现配置解析、日志初始化或工具执行逻辑。新增能力应优先注册到已有边界：

- 新工具：注册 `ToolSpec`。
- 新插件：通过 plugin registry 暴露 hooks/tools/skills。
- 新扩展：实现 `DojoExtension`。
- 新 Dashboard 服务：通过 `dojoagents/dashboard/deps.py` 访问。

## 相关代码

- `dojoagents/agent/runtime.py`
- `dojoagents/config/loader.py`
- `dojoagents/config/models.py`

