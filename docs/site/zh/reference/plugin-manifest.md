# Plugin Manifest

## 状态

插件发现和加载以 `dojoagents/plugins/registry.py` 为准。

## 支持文件

插件目录可以包含：

- `plugin.yaml`
- `.claude-plugin/plugin.json`
- `plugin.json`
- `hooks.json`
- `hooks/hooks.json`
- `__init__.py`

## Manifest 字段

| 字段 | 说明 |
| --- | --- |
| `name` | 插件名 |
| `version` | 版本，默认 `0.1.0` |
| `description` | 描述 |
| `provides_tools` | 工具列表 |
| `provides_hooks` | hook 列表 |

## Hook

有效 hook 名称包括：

- `on_session_start`
- `pre_llm_call`
- `pre_api_request`
- `post_api_request`
- `pre_tool_call`
- `post_tool_call`
- `transform_tool_result`
- `transform_llm_output`
- `post_llm_call`
- `on_session_end`

Claude hook 会通过兼容映射转换。

