# Provider Request Boundary

This page defines the authoritative boundary between Dojo's internal messages and requests sent to
OpenAI-compatible gateways. Internal sessions need to preserve complete semantics, while an external
gateway may accept only a stricter wire schema. Compatibility transformations belong exclusively in
the outbound adapter; they must not leak back into Session, Strands, or tool results.

## 1. Data Flow and Responsibilities

The complete flow is:

```text
Strands / Session
  → Dojo internal messages/tools
  → ProviderRequest (request snapshot)
  → OpenAIRequestAdapter (pure transformation)
  → OpenAITransport (SDK / HTTP / lifecycle)
  → OpenAIResponseAdapter (normal, streaming, and raw-receipt decoding)
  → LLMResult
```

| Component | Owns | Does not own |
| --- | --- | --- |
| Agent / Session | Internal messages, agent and tool names, session round trips | Gateway compatibility |
| `ProviderRequest` | Describes one call; the adapter deep-copies nested messages and tools | Networking, retries, response parsing |
| `OpenAIRequestAdapter` | Message-field policy, tool encoding, omission rules, model IDs, option validation | Network access or input mutation |
| `OpenAITransport` | `AsyncOpenAI`, HTTP client, headers, timeouts, retries, response limits, and shutdown | Message compatibility policy or `LLMResult` conversion |
| `OpenAIResponseAdapter` | Normal/stream/raw responses, reasoning, tool calls, finish reason, and usage | Sending network requests |
| `OpenAICompatibleProvider` | Stable facade orchestrating Request, Transport, and Response | Mutating internal session objects |

The public `LLMProvider.chat()` signature remains unchanged. A transport response handle keeps its
client alive until a normal response is decoded or a stream is fully consumed. Successful completion,
decode failure, and cancellation all trigger bounded, shielded response/client shutdown. A client
must never be closed before its async stream is consumed.

## 2. Internal Messages Are Not Wire Payloads

An internal tool-result message may retain a top-level `name`:

```json
{
  "role": "tool",
  "name": "quote",
  "tool_call_id": "call-1",
  "content": "123.4"
}
```

That field participates in the Strands-to-Dojo round trip and must not be removed by producers or
persistence. The outbound adapter copies each message and, according to policy, removes only the
copy's **top-level** `name`. It never recursively removes fields, so
`tool_calls[].function.name` remains intact.

This boundary guarantees that:

- strict external gateways do not receive an unsupported top-level message `name`;
- the original Session message remains unchanged;
- function names and tool-result names still round-trip correctly;
- logs describe the redacted structure actually sent to the gateway, not the unadapted internal one.

## 3. Compatibility Profiles

`provider_profiles.py` provides three explicit wire profiles:

| Profile | Top-level `name` | Empty `tools` | Stream usage |
| --- | --- | --- | --- |
| `openai_compatible` | omit | omit | include |
| `openai_native` | omit | omit | include |
| `minimal_openai_compatible` | omit | omit | unsupported |

Unknown gateways default to `openai_compatible`. `minimal_openai_compatible` is only for gateways
known to reject `stream_options`.

Both `openai_native` and the default compatible profile omit the message's top-level `name`: the
OpenAI Chat Completions wire schema for tool messages has no such field. They remain separate
profiles so the official endpoint identity is explicit and future wire-proven differences have a
stable home; internal message names are still preserved.

Keeping streaming usage is a compatibility requirement, not an optional optimization. Omitting it
degrades token usage from actual values to estimates and can alter the input to context compression.
Only a gateway profile known not to support the option may use `unsupported`, with an explicit usage
degradation test.

Model-ID behavior is independent of the wire profile: `as_is` preserves the ID and `author_prefix`
adds `author/model` only when needed. `resolve_provider_profile()` returns the wire policy, model-ID
policy, and model catalog together; Provider and ModelContextRegistry consume the same resolution.

Resolution priority is explicit user config, built-in preset declaration, then
`openai_compatible`. An old config with no explicit model policy and an OpenRouter/OrcaRouter URL
temporarily uses a deprecated legacy fallback. This fallback only resolves local configuration and
never sends a probing request.

## 4. Request Options and `extra_body`

The adapter accepts only:

- `temperature`
- `max_tokens`
- `max_completion_tokens`
- `response_format`
- `extra_body`

`extra_body` is an OpenAI SDK encoding channel, not a gateway capability. It cannot override
`model`, `messages`, `tools`, or `stream`. The logical request retains an explicit
`max_completion_tokens`; Transport passes it directly when supported by the installed OpenAI SDK and
falls back to `extra_body` for an older SDK. Wire profiles do not know about SDK encoding details.

The adapter is a pure transformation: identical input produces identical output, with no network
access and no mutation of messages, tools, metadata, or options. Messages and tools are deeply
copied before transformation, so future nested-field cleanup cannot mutate shared Session objects.
Capability probing by retrying a failed request with a different payload is forbidden because it
can create unpredictable duplicate requests.

## 5. Extension and Acceptance Rules

When adding a compatibility profile:

1. Prove the wire difference with an observed request body instead of guessing by provider name.
2. Express the difference through `OpenAIRequestPolicy`, not scattered Provider branches.
3. Add pure-adapter tests for input immutability, ordering, and field policy.
4. Capture real HTTP JSON with `httpx.MockTransport`; SDK mock-argument assertions alone are not enough.
5. Preserve internal round-trip tests, especially tool names and nested `function.name`.
6. If usage support changes, verify usage-quality and compression-policy degradation.

Configuration example:

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

This phase still excludes Session API projection changes, unrelated dead-code cleanup, and token-ledger
algorithm changes.
