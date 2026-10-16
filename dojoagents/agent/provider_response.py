from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from dojoagents.agent.models import LLMResult, ToolCall
from dojoagents.agent.provider_transport import OpenAITransportResponse


_REDACTED_PROVIDER_KEYS = {
    "thought_signature",
    "thoughtSignature",
    "reasoningSignature",
    "signature",
}
_IMAGE_DATA_URL_RE = re.compile(
    r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.*)$",
    re.DOTALL,
)


def redact_provider_response(value: Any, secret: str = "") -> Any:
    """Sanitize provider receipts before persistence or logging."""

    if isinstance(value, float) and not math.isfinite(value):
        return "<non_finite>"
    if isinstance(value, dict):
        return {
            key: (
                "<remote URL omitted>"
                if key in {"file_url", "transcription_url", "video_url"}
                else redact_provider_response(item, secret)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_provider_response(item, secret) for item in value]
    if isinstance(value, str):
        value = value.replace(secret, "<credential omitted>") if secret else value
        return re.sub(
            r'https?://[^\s"<>]+',
            lambda match: (
                urlunsplit(urlsplit(match[0])._replace(query="", fragment=""))
                if any(
                    marker in match[0].lower()
                    for marker in ("x-amz-", "signature=", "access_token=")
                )
                else match[0]
            ),
            value,
        )
    return value


def redact_provider_metadata(value: Any) -> Any:
    if isinstance(value, str):
        match = _IMAGE_DATA_URL_RE.match(value)
        if match:
            return (
                f"[image-data mime={match.group(1).lower()} "
                f"encoded_chars={len(match.group(2))}]"
            )
        return redact_provider_response(value)
    if isinstance(value, dict):
        return {
            key: (
                "[redacted]"
                if key in _REDACTED_PROVIDER_KEYS
                else redact_provider_metadata(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_provider_metadata(item) for item in value]
    return value


def _model_extra_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    model_extra = getattr(obj, "model_extra", None)
    if isinstance(model_extra, dict):
        return dict(model_extra)
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, "model_dump"):
        dumped = obj.model_dump(exclude_none=True)
        return dict(dumped) if isinstance(dumped, dict) else {}
    return {}


def _extract_tool_call_metadata(tc: Any, provider_name: str) -> dict[str, Any]:
    tool_extra = _model_extra_dict(tc)
    function_extra = _model_extra_dict(getattr(tc, "function", None))
    metadata: dict[str, Any] = {}
    if tool_extra or function_extra:
        metadata["provider"] = provider_name
    if tool_extra:
        metadata["tool_call_extra"] = tool_extra
    if function_extra:
        metadata["raw_function_call"] = function_extra
        thought_signature = function_extra.get(
            "thought_signature"
        ) or function_extra.get("thoughtSignature")
        if thought_signature is not None:
            metadata["thought_signature"] = thought_signature
    return metadata


def _usage_dict(usage: Any) -> dict[str, int] | None:
    if usage is None:
        return None
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    total = getattr(usage, "total_tokens", None)
    if prompt is None and completion is None:
        return None
    prompt_i = int(prompt or 0)
    completion_i = int(completion or 0)
    result = {
        "prompt_tokens": prompt_i,
        "completion_tokens": completion_i,
        "total_tokens": int(
            total if total is not None else prompt_i + completion_i
        ),
    }
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    cached_tokens = getattr(prompt_details, "cached_tokens", None)
    if isinstance(cached_tokens, int):
        result["cache_read_tokens"] = cached_tokens
    completion_details = getattr(usage, "completion_tokens_details", None)
    reasoning_tokens = getattr(completion_details, "reasoning_tokens", None)
    if isinstance(reasoning_tokens, int):
        result["reasoning_tokens"] = reasoning_tokens
    return result


def _finish_reason(choice: Any) -> str | None:
    value = getattr(choice, "finish_reason", None)
    return value if isinstance(value, str) else None


class OpenAIResponseAdapter:
    """Convert SDK and raw transport responses into Dojo's LLMResult."""

    async def decode(
        self,
        response: OpenAITransportResponse,
        *,
        provider_name: str,
        api_key: str = "",
        metadata: dict[str, Any] | None = None,
        stream_callback: Callable[[str], None] | None = None,
    ) -> LLMResult:
        async with response:
            if response.is_raw:
                return self._decode_raw(
                    response.value,
                    provider_name=provider_name,
                    api_key=api_key,
                )
            if response.is_stream:
                return await self._decode_stream(
                    response.value,
                    provider_name=provider_name,
                    metadata=metadata,
                    stream_callback=stream_callback,
                )
            return self._decode_normal(
                response.value,
                provider_name=provider_name,
            )

    @staticmethod
    def _decode_raw(
        response: Any,
        *,
        provider_name: str,
        api_key: str,
    ) -> LLMResult:
        text = response.content.decode("utf-8", errors="backslashreplace")
        try:
            body = json.loads(
                text,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(value)
                ),
            )
        except (ValueError, RecursionError):
            body = {"_unparsed_response": text}
        body = redact_provider_response(body, api_key)
        choices = body.get("choices") if isinstance(body, dict) else None
        first = (
            choices[0]
            if isinstance(choices, list)
            and choices
            and isinstance(choices[0], dict)
            else {}
        )
        message = first.get("message") or {}
        content = message.get("content") if isinstance(message, dict) else None
        result_metadata = {
            "provider": provider_name,
            "raw_response": {
                "http_status": response.status_code,
                "response": body,
            },
            "finish_reason": first.get("finish_reason"),
        }
        if isinstance(body, dict) and isinstance(body.get("usage"), dict):
            result_metadata["usage"] = body["usage"]
        return LLMResult(
            content=content if isinstance(content, str) else "",
            metadata=result_metadata,
        )

    @staticmethod
    def _decode_normal(response: Any, *, provider_name: str) -> LLMResult:
        choice = response.choices[0]
        message = choice.message
        reasoning_content = getattr(message, "reasoning_content", None) or (
            message.model_extra.get("reasoning_content")
            if hasattr(message, "model_extra") and message.model_extra
            else None
        )
        final_tool_calls = []
        if message.tool_calls:
            for tool_call in message.tool_calls:
                arguments: dict[str, Any] = {}
                if tool_call.function.arguments:
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {
                            "raw_arguments": tool_call.function.arguments,
                        }
                final_tool_calls.append(
                    ToolCall(
                        id=tool_call.id,
                        name=tool_call.function.name,
                        arguments=arguments,
                        metadata=_extract_tool_call_metadata(
                            tool_call,
                            provider_name,
                        ),
                    )
                )
        result_metadata: dict[str, Any] = {
            "provider": provider_name,
            "reasoning_content": reasoning_content or "",
        }
        finish_reason = _finish_reason(choice)
        if finish_reason is not None:
            result_metadata["finish_reason"] = finish_reason
        usage = _usage_dict(getattr(response, "usage", None))
        if usage is not None:
            result_metadata["usage"] = usage
        else:
            result_metadata["usage_available"] = False
        return LLMResult(
            content=message.content or "",
            tool_calls=final_tool_calls,
            metadata=result_metadata,
        )

    @staticmethod
    async def _decode_stream(
        stream: Any,
        *,
        provider_name: str,
        metadata: dict[str, Any] | None,
        stream_callback: Callable[[str], None] | None,
    ) -> LLMResult:
        full_content: list[str] = []
        full_reasoning: list[str] = []
        tool_calls_buffer: dict[int, dict[str, Any]] = {}
        stream_usage: dict[str, int] | None = None
        finish_reason: str | None = None
        event_sink = (metadata or {}).get("_dojo_event_sink")
        reasoning_started = False
        reasoning_ended = False
        content_started = False

        async for chunk in stream:
            chunk_usage = _usage_dict(getattr(chunk, "usage", None))
            if chunk_usage is not None:
                stream_usage = chunk_usage
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            finish_reason = _finish_reason(choice) or finish_reason
            delta = choice.delta
            if event_sink is not None:
                await event_sink.wait_for_capacity()
            reasoning_delta = getattr(delta, "reasoning_content", None) or (
                delta.model_extra.get("reasoning_content")
                if hasattr(delta, "model_extra") and delta.model_extra
                else None
            )
            if reasoning_delta:
                full_reasoning.append(reasoning_delta)
                if event_sink is not None and not content_started:
                    if not reasoning_started:
                        event_sink.thinking_start()
                        reasoning_started = True
                    event_sink.thinking_delta(reasoning_delta)
            content_delta = delta.content or ""
            if content_delta:
                if (
                    event_sink is not None
                    and reasoning_started
                    and not reasoning_ended
                ):
                    event_sink.thinking_end()
                    reasoning_ended = True
                content_started = True
                full_content.append(content_delta)
                if stream_callback is not None:
                    stream_callback(content_delta)
            if delta.tool_calls:
                for tool_call_delta in delta.tool_calls:
                    index = tool_call_delta.index
                    if index not in tool_calls_buffer:
                        tool_calls_buffer[index] = {
                            "id": "",
                            "name": "",
                            "arguments": "",
                            "metadata": {},
                        }
                    buffered = tool_calls_buffer[index]
                    if tool_call_delta.id:
                        buffered["id"] = tool_call_delta.id
                    if (
                        tool_call_delta.function
                        and tool_call_delta.function.name
                    ):
                        buffered["name"] = tool_call_delta.function.name
                    if (
                        tool_call_delta.function
                        and tool_call_delta.function.arguments
                    ):
                        buffered["arguments"] += (
                            tool_call_delta.function.arguments
                        )
                    buffered["metadata"].update(
                        _extract_tool_call_metadata(
                            tool_call_delta,
                            provider_name,
                        )
                    )

        if event_sink is not None and reasoning_started and not reasoning_ended:
            event_sink.thinking_end()

        final_tool_calls = []
        for _, buffered in sorted(tool_calls_buffer.items()):
            arguments: dict[str, Any] = {}
            if buffered["arguments"].strip():
                try:
                    arguments = json.loads(buffered["arguments"])
                except json.JSONDecodeError:
                    arguments = {"raw_arguments": buffered["arguments"]}
            final_tool_calls.append(
                ToolCall(
                    id=buffered["id"],
                    name=buffered["name"],
                    arguments=arguments,
                    metadata=dict(buffered["metadata"]),
                )
            )

        result_metadata: dict[str, Any] = {
            "provider": provider_name,
            "reasoning_content": "".join(full_reasoning),
            "reasoning_streamed": bool(full_reasoning),
        }
        if finish_reason is not None:
            result_metadata["finish_reason"] = finish_reason
        if stream_usage is not None:
            result_metadata["usage"] = stream_usage
        else:
            result_metadata["usage_available"] = False
        return LLMResult(
            content="".join(full_content),
            tool_calls=final_tool_calls,
            metadata=result_metadata,
        )
