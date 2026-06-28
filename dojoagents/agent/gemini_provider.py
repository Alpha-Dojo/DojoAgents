from __future__ import annotations

import json
import os
from typing import Any, Callable

import httpx

from dojoagents.agent.context_length import ContextLengthExceededError, parse_context_length_error
from dojoagents.agent.models import LLMResult, ToolCall
from dojoagents.agent.provider_state import ProviderConversationState
from dojoagents.logging import LOGGER

_DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


def _normalize_base_url(base_url: str | None) -> str:
    normalized = (base_url or _DEFAULT_GEMINI_BASE_URL).rstrip("/")
    if normalized.endswith("/openai"):
        normalized = normalized[: -len("/openai")]
    return normalized


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(exclude_none=True)
        return dict(dumped) if isinstance(dumped, dict) else {}
    return {}


def _json_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _tool_response_payload(message: dict[str, Any]) -> dict[str, Any]:
    content = message.get("content")
    if isinstance(content, str):
        parsed = _json_payload(content)
        if parsed:
            return parsed
        return {"content": content}
    if isinstance(content, dict):
        return dict(content)
    return {"content": "" if content is None else str(content)}


def _build_function_declarations(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    declarations: list[dict[str, Any]] = []
    for tool in tools:
        schema = dict(tool.get("parameters") or {"type": "object", "properties": {}})
        schema.setdefault("type", "object")
        declarations.append(
            {
                "name": tool.get("name") or "tool",
                "description": tool.get("description") or "",
                "parametersJsonSchema": schema,
            }
        )
    if not declarations:
        return []
    return [{"functionDeclarations": declarations}]


def _assistant_parts_from_message(
    message: dict[str, Any],
    *,
    provider_state: ProviderConversationState | None,
    provider_name: str,
    model: str,
    session_id: str,
) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    content = message.get("content")
    if isinstance(content, str) and content:
        parts.append({"text": content})

    tool_calls = message.get("tool_calls") or []
    if not tool_calls:
        return parts

    native_contents: list[dict[str, Any]] = []
    for tool_call in tool_calls:
        metadata = dict(tool_call.get("metadata") or {})
        native_content = metadata.get("native_model_content")
        if not native_content and provider_state is not None:
            tool_call_id = str(tool_call.get("id") or "")
            if tool_call_id:
                native_content = provider_state.metadata_for_tool_call(
                    provider=provider_name,
                    model=model,
                    session_id=session_id,
                    tool_call_id=tool_call_id,
                ).get("native_model_content")
        if isinstance(native_content, dict):
            native_contents.append(native_content)

    if native_contents:
        first = native_contents[0]
        if all(candidate == first for candidate in native_contents[1:]):
            stored_parts = first.get("parts")
            if isinstance(stored_parts, list):
                return [dict(part) for part in stored_parts if isinstance(part, dict)]

    for tool_call in tool_calls:
        function = tool_call.get("function") or {}
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            try:
                args = json.loads(arguments)
            except json.JSONDecodeError:
                args = {}
        elif isinstance(arguments, dict):
            args = dict(arguments)
        else:
            args = {}
        function_call = {
            "name": function.get("name") or "tool",
            "args": args,
        }
        metadata = dict(tool_call.get("metadata") or {})
        raw_function_call = metadata.get("raw_function_call")
        if isinstance(raw_function_call, dict):
            function_call.update(raw_function_call)
        elif metadata.get("thought_signature"):
            function_call["thoughtSignature"] = metadata["thought_signature"]
        elif metadata.get("thoughtSignature"):
            function_call["thoughtSignature"] = metadata["thoughtSignature"]
        parts.append({"functionCall": function_call})
    return parts


def _messages_to_gemini_request(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]],
    model: str,
    session_id: str,
    provider_state: ProviderConversationState | None,
    provider_name: str,
) -> dict[str, Any]:
    system_blocks: list[str] = []
    contents: list[dict[str, Any]] = []

    for message in messages:
        role = str(message.get("role") or "")
        if role == "system":
            content = message.get("content")
            if isinstance(content, str) and content:
                system_blocks.append(content)
            continue

        if role == "user":
            content = message.get("content")
            text = content if isinstance(content, str) else ""
            contents.append({"role": "user", "parts": [{"text": text}]})
            continue

        if role == "assistant":
            parts = _assistant_parts_from_message(
                message,
                provider_state=provider_state,
                provider_name=provider_name,
                model=model,
                session_id=session_id,
            )
            if parts:
                contents.append({"role": "model", "parts": parts})
            continue

        if role == "tool":
            tool_name = str(message.get("name") or "tool")
            payload = _tool_response_payload(message)
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": tool_name,
                                "response": payload,
                            }
                        }
                    ],
                }
            )

    body: dict[str, Any] = {"contents": contents}
    if system_blocks:
        body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_blocks)}]}
    gemini_tools = _build_function_declarations(tools)
    if gemini_tools:
        body["tools"] = gemini_tools
        body["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}
    return body


def _extract_usage(payload: dict[str, Any]) -> dict[str, int] | None:
    usage = payload.get("usageMetadata")
    if not isinstance(usage, dict):
        return None
    prompt = usage.get("promptTokenCount")
    completion = usage.get("candidatesTokenCount")
    total = usage.get("totalTokenCount")
    if not isinstance(prompt, int) and not isinstance(completion, int):
        return None
    prompt_i = int(prompt or 0)
    completion_i = int(completion or 0)
    return {
        "prompt_tokens": prompt_i,
        "completion_tokens": completion_i,
        "total_tokens": int(total if isinstance(total, int) else prompt_i + completion_i),
    }


def _iter_candidate_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = payload.get("candidates")
    candidate = candidates[0] if isinstance(candidates, list) and candidates else {}
    content = candidate.get("content") if isinstance(candidate, dict) else {}
    content_dict = dict(content) if isinstance(content, dict) else {}
    parts = content_dict.get("parts")
    return [dict(part) for part in parts if isinstance(part, dict)] if isinstance(parts, list) else []


def _merge_text_value(existing: Any, new_value: Any) -> str | None:
    if not isinstance(new_value, str):
        return existing if isinstance(existing, str) else None
    if not isinstance(existing, str) or not existing:
        return new_value
    if new_value.startswith(existing):
        return new_value
    if existing.startswith(new_value):
        return existing
    return existing + new_value


def _merge_args_value(existing: Any, new_value: Any) -> Any:
    if isinstance(existing, dict) and isinstance(new_value, dict):
        merged = dict(existing)
        merged.update(new_value)
        return merged
    if isinstance(new_value, str):
        if isinstance(existing, str):
            if new_value.startswith(existing):
                return new_value
            if existing.startswith(new_value):
                return existing
            return existing + new_value
        return new_value
    if new_value is not None:
        return new_value
    return existing


def _merge_stream_payload(aggregate: dict[str, Any] | None, payload: dict[str, Any]) -> dict[str, Any]:
    if aggregate is None:
        return _as_dict(payload)

    merged = _as_dict(aggregate)
    payload_dict = _as_dict(payload)

    payload_candidates = payload_dict.get("candidates")
    if isinstance(payload_candidates, list) and payload_candidates:
        merged_candidates = merged.setdefault("candidates", [])
        if not isinstance(merged_candidates, list):
            merged_candidates = []
            merged["candidates"] = merged_candidates
        for idx, candidate in enumerate(payload_candidates):
            if not isinstance(candidate, dict):
                continue
            while len(merged_candidates) <= idx:
                merged_candidates.append({})
            target_candidate = merged_candidates[idx]
            if not isinstance(target_candidate, dict):
                target_candidate = {}
                merged_candidates[idx] = target_candidate
            for key, value in candidate.items():
                if key != "content":
                    target_candidate[key] = value
                    continue
                if not isinstance(value, dict):
                    target_candidate[key] = value
                    continue
                target_content = target_candidate.setdefault("content", {})
                if not isinstance(target_content, dict):
                    target_content = {}
                    target_candidate["content"] = target_content
                for content_key, content_value in value.items():
                    if content_key != "parts":
                        target_content[content_key] = content_value
                        continue
                    if not isinstance(content_value, list):
                        target_content[content_key] = content_value
                        continue
                    target_parts = target_content.setdefault("parts", [])
                    if not isinstance(target_parts, list):
                        target_parts = []
                        target_content["parts"] = target_parts
                    for part_idx, part in enumerate(content_value):
                        if not isinstance(part, dict):
                            continue
                        while len(target_parts) <= part_idx:
                            target_parts.append({})
                        target_part = target_parts[part_idx]
                        if not isinstance(target_part, dict):
                            target_part = {}
                            target_parts[part_idx] = target_part
                        for part_key, part_value in part.items():
                            if part_key == "text":
                                merged_text = _merge_text_value(target_part.get("text"), part_value)
                                if merged_text is not None:
                                    target_part["text"] = merged_text
                                continue
                            if part_key == "functionCall" and isinstance(part_value, dict):
                                target_fc = target_part.setdefault("functionCall", {})
                                if not isinstance(target_fc, dict):
                                    target_fc = {}
                                    target_part["functionCall"] = target_fc
                                for fc_key, fc_value in part_value.items():
                                    if fc_key == "args":
                                        target_fc["args"] = _merge_args_value(target_fc.get("args"), fc_value)
                                    else:
                                        target_fc[fc_key] = fc_value
                                continue
                            target_part[part_key] = part_value

    for top_key, top_value in payload_dict.items():
        if top_key == "candidates":
            continue
        merged[top_key] = top_value
    return merged


async def _iter_sse_payloads(response: Any) -> Any:
    data_lines: list[str] = []
    async for raw_line in response.aiter_lines():
        line = raw_line.strip()
        if not line:
            if not data_lines:
                continue
            payload_text = "\n".join(data_lines).strip()
            data_lines = []
            if not payload_text or payload_text == "[DONE]":
                continue
            parsed = json.loads(payload_text)
            if isinstance(parsed, dict):
                yield parsed
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())

    if data_lines:
        payload_text = "\n".join(data_lines).strip()
        if payload_text and payload_text != "[DONE]":
            parsed = json.loads(payload_text)
            if isinstance(parsed, dict):
                yield parsed


def _emit_stream_deltas(
    payload: dict[str, Any],
    *,
    stream_callback: Callable[[str], None] | None,
    event_sink: Any,
    seen_text_lengths: dict[int, int],
    seen_reasoning_lengths: dict[int, int],
    reasoning_started: bool,
) -> bool:
    for idx, part in enumerate(_iter_candidate_parts(payload)):
        text = part.get("text")
        if not isinstance(text, str) or not text:
            continue
        is_reasoning = bool(part.get("thought"))
        seen_lengths = seen_reasoning_lengths if is_reasoning else seen_text_lengths
        previous_length = seen_lengths.get(idx, 0)
        if len(text) < previous_length:
            previous_length = 0
        if len(text) <= previous_length:
            continue
        delta = text[previous_length:]
        seen_lengths[idx] = len(text)
        if is_reasoning:
            if event_sink is None:
                continue
            if not reasoning_started:
                event_sink.thinking_start()
                reasoning_started = True
            event_sink.thinking_delta(delta)
            continue
        if stream_callback is not None:
            stream_callback(delta)
    return reasoning_started


def _parse_response_payload(
    payload: dict[str, Any],
    *,
    provider_state: ProviderConversationState | None,
    session_id: str,
    model: str,
) -> LLMResult:
    candidates = payload.get("candidates")
    candidate = candidates[0] if isinstance(candidates, list) and candidates else {}
    content = candidate.get("content") if isinstance(candidate, dict) else {}
    content_dict = dict(content) if isinstance(content, dict) else {}
    parts = content_dict.get("parts")
    parts_list = parts if isinstance(parts, list) else []

    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    for idx, part in enumerate(parts_list):
        if not isinstance(part, dict):
            continue
        if part.get("thought") and isinstance(part.get("text"), str):
            reasoning_parts.append(part["text"])
            continue
        if isinstance(part.get("text"), str):
            text_parts.append(part["text"])
        function_call = part.get("functionCall")
        if not isinstance(function_call, dict):
            continue
        tool_call_id = str(function_call.get("id") or f"gemini-call-{idx + 1}")
        arguments = function_call.get("args")
        if isinstance(arguments, dict):
            args_dict = dict(arguments)
        elif isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError:
                parsed = {}
            args_dict = dict(parsed) if isinstance(parsed, dict) else {}
        else:
            args_dict = {}
        metadata = {
            "provider": "gemini",
            "native_state_key": tool_call_id,
            "native_model_content": dict(content_dict),
            "raw_function_call": dict(function_call),
        }
        thought_signature = function_call.get("thoughtSignature") or function_call.get("thought_signature")
        if thought_signature is not None:
            metadata["thought_signature"] = thought_signature
        call = ToolCall(
            id=tool_call_id,
            name=str(function_call.get("name") or "tool"),
            arguments=args_dict,
            metadata=metadata,
        )
        tool_calls.append(call)
        if provider_state is not None:
            provider_state.record_tool_call(
                provider="gemini",
                model=model,
                session_id=session_id,
                tool_call_id=tool_call_id,
                tool_name=call.name,
                arguments=call.arguments,
                native_model_content=content_dict,
            )

    result_text = "".join(text_parts)
    if tool_calls:
        result_text = ""

    result_metadata: dict[str, Any] = {
        "provider": "gemini",
        "reasoning_content": "".join(reasoning_parts),
    }
    usage = _extract_usage(payload)
    if usage is not None:
        result_metadata["usage"] = usage
    else:
        result_metadata["usage_available"] = False
    return LLMResult(content=result_text, tool_calls=tool_calls, metadata=result_metadata)


class GeminiNativeProvider:
    name = "gemini"

    def __init__(self, *, api_key: str | None = None, api_key_env: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key or (os.getenv(api_key_env) if api_key_env else None)
        self.base_url = _normalize_base_url(base_url)

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        model: str,
        stream: bool = False,
        metadata: dict | None = None,
        stream_callback: Callable[[str], None] | None = None,
    ) -> LLMResult:
        if not self.api_key:
            return LLMResult(
                content=("Gemini provider is configured without an API key. " "Set the configured api_key_env before making live calls."),
                metadata={"provider": self.name, "live": False},
            )

        invocation_state = metadata or {}
        session_id = str(invocation_state.get("session_id") or "")
        provider_state = invocation_state.get("_dojo_provider_state")
        if not isinstance(provider_state, ProviderConversationState):
            provider_state = None
        LOGGER.info(
            "GeminiNativeProvider.chat start: model=%s session_id=%s stream=%s tools=%d messages=%d event_sink=%s provider_state=%s base_url=%s",
            model,
            session_id,
            stream,
            len(tools),
            len(messages),
            bool(invocation_state.get("_dojo_event_sink")),
            provider_state is not None,
            self.base_url,
        )

        body = _messages_to_gemini_request(
            messages,
            tools=tools,
            model=model,
            session_id=session_id,
            provider_state=provider_state,
            provider_name=self.name,
        )
        event_sink = invocation_state.get("_dojo_event_sink")

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                allow_streaming = stream and not tools
                if stream and tools:
                    LOGGER.info(
                        "GeminiNativeProvider switching to non-stream tool-planning request: model=%s session_id=%s tools=%d",
                        model,
                        session_id,
                        len(tools),
                    )
                if allow_streaming:
                    stream_url = f"{self.base_url}/models/{model}:streamGenerateContent"
                    aggregate_payload: dict[str, Any] | None = None
                    seen_text_lengths: dict[int, int] = {}
                    seen_reasoning_lengths: dict[int, int] = {}
                    reasoning_started = False
                    chunk_count = 0
                    text_delta_count = 0
                    reasoning_delta_count = 0
                    function_call_chunks = 0
                    LOGGER.info(
                        "GeminiNativeProvider opening streaming request: model=%s session_id=%s url=%s",
                        model,
                        session_id,
                        stream_url,
                    )
                    async with client.stream("POST", stream_url, params={"alt": "sse", "key": self.api_key}, json=body) as response:
                        response.raise_for_status()
                        async for payload in _iter_sse_payloads(response):
                            chunk_count += 1
                            before_text = sum(seen_text_lengths.values())
                            before_reasoning = sum(seen_reasoning_lengths.values())
                            aggregate_payload = _merge_stream_payload(aggregate_payload, payload)
                            chunk_function_calls = sum(1 for part in _iter_candidate_parts(payload) if isinstance(part.get("functionCall"), dict))
                            if chunk_function_calls:
                                function_call_chunks += 1
                            reasoning_started = _emit_stream_deltas(
                                payload,
                                stream_callback=stream_callback,
                                event_sink=event_sink,
                                seen_text_lengths=seen_text_lengths,
                                seen_reasoning_lengths=seen_reasoning_lengths,
                                reasoning_started=reasoning_started,
                            )
                            after_text = sum(seen_text_lengths.values())
                            after_reasoning = sum(seen_reasoning_lengths.values())
                            if after_text > before_text:
                                text_delta_count += 1
                            if after_reasoning > before_reasoning:
                                reasoning_delta_count += 1
                            if chunk_count <= 3 or after_text > before_text or after_reasoning > before_reasoning:
                                LOGGER.debug(
                                    "Gemini streaming chunk: model=%s session_id=%s chunk=%d text_chars=%d reasoning_chars=%d function_calls=%d has_candidates=%s",
                                    model,
                                    session_id,
                                    chunk_count,
                                    after_text,
                                    after_reasoning,
                                    chunk_function_calls,
                                    bool(payload.get("candidates")),
                                )
                    if aggregate_payload is None:
                        raise RuntimeError("Gemini returned an empty streaming response")
                    result = _parse_response_payload(
                        aggregate_payload,
                        provider_state=provider_state,
                        session_id=session_id,
                        model=model,
                    )
                    if reasoning_started:
                        if event_sink is not None:
                            event_sink.thinking_end()
                        result.metadata["reasoning_streamed"] = True
                    LOGGER.info(
                        "GeminiNativeProvider streaming response complete: model=%s session_id=%s chunks=%d text_delta_chunks=%d reasoning_delta_chunks=%d final_content_len=%d tool_calls=%d reasoning_len=%d",  # noqa
                        model,
                        session_id,
                        chunk_count,
                        text_delta_count,
                        reasoning_delta_count,
                        len(result.content or ""),
                        len(result.tool_calls),
                        len(str(result.metadata.get("reasoning_content") or "")),
                    )
                    if function_call_chunks:
                        LOGGER.info(
                            "GeminiNativeProvider observed function calls in streaming response: model=%s session_id=%s chunks_with_function_calls=%d aggregated_tool_calls=%d",
                            model,
                            session_id,
                            function_call_chunks,
                            len(result.tool_calls),
                        )
                    return result

                url = f"{self.base_url}/models/{model}:generateContent"
                LOGGER.info(
                    "GeminiNativeProvider sending non-stream request: model=%s session_id=%s url=%s tools=%d",
                    model,
                    session_id,
                    url,
                    len(tools),
                )
                response = await client.post(url, params={"key": self.api_key}, json=body)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            err_text = exc.response.text
            max_context, requested = parse_context_length_error(err_text)
            if max_context is not None or requested is not None:
                raise ContextLengthExceededError(err_text, max_context=max_context, requested_tokens=requested) from exc
            LOGGER.exception("Error calling Gemini API: %s", err_text)
            raise
        except Exception:
            LOGGER.exception("Error calling Gemini API")
            raise

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Gemini returned a non-object response")
        result = _parse_response_payload(
            payload,
            provider_state=provider_state,
            session_id=session_id,
            model=model,
        )
        LOGGER.info(
            "GeminiNativeProvider non-stream response complete: model=%s session_id=%s content_len=%d tool_calls=%d reasoning_len=%d usage_available=%s",
            model,
            session_id,
            len(result.content or ""),
            len(result.tool_calls),
            len(str(result.metadata.get("reasoning_content") or "")),
            "usage" in result.metadata,
        )
        return result
