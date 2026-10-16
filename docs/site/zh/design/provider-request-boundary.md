# Provider 请求边界

本页定义 Dojo 内部消息与 OpenAI-compatible 网关请求之间的权威边界。它解决的核心问题是：
内部会话需要保存完整语义，而外部网关可能只接受更严格的 wire schema。兼容处理只能发生在
出站适配器中，不能反向污染 Session、Strands 或工具结果。

## 1. 数据流与职责

当前完整链路为：

```text
Strands / Session
  → Dojo 内部 messages/tools
  → ProviderRequest（请求快照）
  → OpenAIRequestAdapter（纯转换）
  → OpenAITransport（SDK / HTTP / 生命周期）
  → OpenAIResponseAdapter（普通、流式、raw receipt 解码）
  → LLMResult
```

| 组件 | 职责 | 不负责 |
| --- | --- | --- |
| Agent / Session | 保存内部消息、Agent 名称、工具名称及会话往返语义 | 外部网关兼容 |
| `ProviderRequest` | 描述一次调用；Adapter 对嵌套消息和工具做深拷贝 | 网络、重试、响应解析 |
| `OpenAIRequestAdapter` | 消息字段策略、tools 编码、空字段省略、模型 ID、请求选项验证 | 网络访问、修改输入 |
| `OpenAITransport` | `AsyncOpenAI`、HTTP client、headers、超时、重试、响应大小和资源关闭 | 消息兼容策略、`LLMResult` 转换 |
| `OpenAIResponseAdapter` | 普通/流式/raw 响应、reasoning、tool calls、finish reason 和 usage | 发起网络请求 |
| `OpenAICompatibleProvider` | 保持公共门面并编排 Request、Transport、Response | 修改内部会话对象 |

`LLMProvider.chat()` 的公共签名保持不变。Transport 返回的响应句柄持有 client；普通响应完成、
流式响应完全消费、解析失败或任务取消后，Response Adapter 都会触发有界且受保护的资源关闭。
因此不能在返回 async stream 前关闭 client，也不能让取消路径遗留 response/client。

## 2. 内部消息不是 wire payload

内部工具结果允许保留顶层 `name`：

```json
{
  "role": "tool",
  "name": "quote",
  "tool_call_id": "call-1",
  "content": "123.4"
}
```

该字段参与 Strands 与 Dojo 消息的往返，不得在生产者或持久化层删除。出站适配器会复制每条
消息，并按策略只删除副本的**顶层** `name`。它不会递归删除字段，因此
`tool_calls[].function.name` 必须保留。

这条边界同时保证：

- 外部严格网关不会收到不支持的消息顶层 `name`；
- Session 中的原始消息不变；
- 工具调用函数名和工具结果名称仍可正常往返；
- 日志描述实际外发的已脱敏结构，而不是未经适配的内部结构。

## 3. Compatibility Profile

`provider_profiles.py` 提供三个显式 wire profile：

| Profile | 顶层 `name` | 空 `tools` | stream usage |
| --- | --- | --- | --- |
| `openai_compatible` | omit | omit | include |
| `openai_native` | omit | omit | include |
| `minimal_openai_compatible` | omit | omit | unsupported |

未知网关默认使用 `openai_compatible`。`minimal_openai_compatible` 只适用于已经确认拒绝
`stream_options` 的网关。

`openai_native` 与默认兼容模式都会删除消息顶层 `name`：OpenAI Chat Completions 的 tool
message wire schema 不包含该字段。两者仍保留为独立 profile，以便表达官方端点身份并承载未来经过
wire 证据确认的差异；内部消息中的名称不会因此丢失。

保留流式 usage 是兼容性要求，而不是可有可无的优化。省略它会让 token usage 从实际值降级为
估算值，并可能改变上下文压缩策略的输入。只有明确不支持该参数的网关 profile 才能使用
`unsupported`，且必须补充 usage 降级测试。

模型 ID 策略独立于 wire profile：`as_is` 保留模型 ID，`author_prefix` 在必要时拼接
`author/model`。`resolve_provider_profile()` 同时返回 wire policy、模型 ID 策略和模型目录类型，
Provider 与 ModelContextRegistry 必须共用该结果。

配置优先级是用户显式配置、内置 preset 声明、最后回落到 `openai_compatible`。旧配置若没有显式
模型策略但 URL 指向 OpenRouter/OrcaRouter，会暂时启用带弃用警告的 legacy fallback；该 fallback
只解析本地配置，不发送探测请求。

## 4. 请求选项与 `extra_body`

适配器只接受：

- `temperature`
- `max_tokens`
- `max_completion_tokens`
- `response_format`
- `extra_body`

`extra_body` 是 OpenAI SDK 的编码通道，不是网关 capability。它不能覆盖 `model`、
`messages`、`tools` 或 `stream`。逻辑请求保留显式 `max_completion_tokens`。Transport 根据
当前 OpenAI SDK 的调用签名决定直接传参，或为旧 SDK 映射到 `extra_body`；wire profile 不感知
SDK 编码差异。

适配器是纯函数式转换：相同输入得到相同输出，不访问网络，不修改消息、工具、metadata 或
options。消息与工具会深层复制后再转换，后续增加嵌套字段清洗也不能污染 Session 中的共享对象。
禁止通过“请求失败后换一种 payload 重试”探测网关能力，因为该做法会产生不可预测的重复请求。

## 5. 扩展和验收规则

新增兼容 profile 时：

1. 先用真实 wire body 证明差异，而不是按服务商名称猜测；
2. 在 `OpenAIRequestPolicy` 表达差异，避免散落 Provider 条件分支；
3. 为纯 Adapter 增加输入不变性、顺序和字段策略测试；
4. 用 `httpx.MockTransport` 捕获真实 HTTP JSON，不能只断言 SDK mock 参数；
5. 保留内部消息往返测试，特别是工具名和嵌套 `function.name`；
6. 若改变 usage 支持，必须验证 usage quality 与压缩策略的降级行为。

配置示例：

```yaml
llm_provider:
  providers:
    custom_gateway:
      base_url: https://gateway.example/v1
      compatibility_profile: openai_compatible
      model_id_policy: as_is
      timeout: 120
      max_retries: 2
      max_response_bytes: 8388608
```

本阶段仍不包含：Session API 投影调整、无关死代码清理或 token ledger 算法修改。
