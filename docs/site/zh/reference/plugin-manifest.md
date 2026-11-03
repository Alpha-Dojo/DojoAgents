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
| `version` | 版本，默认 `0.2.0` |
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

## 可选 Adanos 研究插件

内置 `adanos` 插件仅在进程环境设置 `ADANOS_API_KEY` 时注册
`adanos_sentiment`。请在启动前通过 shell 或密钥管理器设置；修改或删除
密钥后需重启。密钥不会作为工具参数传入，也不改变默认配置。

[Adanos](https://adanos.org/) 是提供免费方案的商业 API。可用数据源、历史
范围和配额取决于账户方案。401/403/429 返回错误，不转换为中性情绪。
参见 [API 文档](https://api.adanos.org/docs)。

数据源：`reddit_stocks`、`reddit_crypto`、`x_stocks`、`news_stocks`、
`polymarket_stocks`。操作：`asset`、`trending`、`market`、`compare`。

```json
{"source":"news_stocks","operation":"asset","asset":"BRK","from":"2026-10-01","to":"2026-10-02"}
```

比较时传入 `assets` 数组，例如 `["BTC", "ETH"]`。News 使用公司键，
例如 `BRK` 而不是 `BRK.B`。`from`/`to` 为包含边界的 UTC 日期，不支持
`days`。工具保留原始响应及来源、URL、日期，不重映射分数。仅 Reddit
支持加密资产。结果只是额外研究证据，不是价格源、时间点回测数据或独立
买卖信号。

