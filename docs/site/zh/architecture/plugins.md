# Plugins 架构

## 目标

Plugin 系统允许 DojoAgents 从内置插件和用户插件目录中加载 tools、hooks、skills、MCP 配置和 agent 配置。

## 发现路径

- 内置插件：`dojoagents/plugins/built_in/`
- 用户插件：`~/.dojo/plugins`

## Manifest

当前 registry 支持：

- `plugin.yaml`
- `.claude-plugin/plugin.json`
- `plugin.json`
- `hooks.json`
- `hooks/hooks.json`
- `__init__.py`

## Hook

插件 hooks 必须使用 `dojoagents/plugins/registry.py::VALID_HOOKS` 中定义的名称。Claude hook 名称会通过兼容映射转换为 Dojo hook。

## 深入阅读

- [Plugin Manifest Reference](../reference/plugin-manifest.md)
- [添加工具](../development/adding-tools.md)
