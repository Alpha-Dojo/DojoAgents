# 安全

## Secrets

- 不要在文档、日志、Dashboard response、memory 或 tool result 中输出 API key、provider token、webhook secret。
- Dashboard 配置接口必须使用 redacted config。
- 配置文件可使用环境变量占位保存密钥。

## 工具执行

- 工具必须通过 `ToolExecutor` 和 sandbox policy。
- 不要绕过 `SandboxPolicy` 执行 terminal/code/tool。
- 有副作用的工具应明确返回 `resource_changes`，让 UI 和调用者知道发生了什么。

## Gateway

- Webhook 应部署在可信网络或前置认证层后。
- Pairing 默认应偏保守。
- 平台 token 应存放在配置或环境变量中，不写入文档和日志。

## Dashboard

如果绑定 `0.0.0.0` 或部署到公网，需要额外的认证、访问控制和网络隔离。

