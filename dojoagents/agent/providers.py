import email.utils
import json
import logging
import math
import random
import re
import time
import uuid

import anyio
from urllib.parse import urlsplit, urlunsplit

import httpx
from typing import Any, Protocol, Callable
from dojoagents.agent.context_length import ContextLengthExceededError, parse_context_length_error
from dojoagents.logging import LOGGER
from dojoagents.agent.models import LLMResult, ToolCall
from dojoagents.agent.events import emit_stream_delta
from dojoagents.agent.telemetry import LLMCallEvent, LLMRequestEvent, current_run_id, emit

_REDACTED_PROVIDER_KEYS = {"thought_signature", "thoughtSignature", "reasoningSignature", "signature"}
_IMAGE_DATA_URL_RE = re.compile(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.*)$", re.DOTALL)


def redact_provider_response(value: Any, secret: str = "") -> Any:
    """Sanitize provider receipts before persistence or logging."""
    if isinstance(value, float) and not math.isfinite(value):
        return "<non_finite>"
    if isinstance(value, dict):
        return {key: ("<remote URL omitted>" if key in {"file_url", "transcription_url", "video_url"} else redact_provider_response(item, secret)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_provider_response(item, secret) for item in value]
    if isinstance(value, str):
        value = value.replace(secret, "<credential omitted>") if secret else value
        return re.sub(
            r'https?://[^\s"<>]+',
            lambda match: (
                urlunsplit(urlsplit(match[0])._replace(query="", fragment=""))
                if any(marker in match[0].lower() for marker in ("x-amz-", "signature=", "access_token="))
                else match[0]
            ),
            value,
        )
    return value


def _log_model_request(event: str, context: dict, *, level: int = logging.INFO, **fields) -> None:
    data = {**context, **fields, "event": event}
    emit(
        LLMRequestEvent(
            run_id=context["run_id"],
            provider=context["provider"],
            model=context["model"],
            event=event,
            attempt=context["attempt"],
            outcome=fields.get("outcome", ""),
            elapsed_ms=fields.get("elapsed_ms", 0),
        )
    )
    LOGGER.log(level, "%s %s", event, json.dumps(data, ensure_ascii=False, separators=(",", ":")), extra={"llm_request": data})


def _retryable_model_error(error: Exception) -> bool:
    from openai import APIConnectionError, APIStatusError

    if isinstance(error, APIConnectionError):
        return True
    if not isinstance(error, APIStatusError):
        return False
    hint = error.response.headers.get("x-should-retry")
    if hint in {"true", "false"}:
        return hint == "true"
    return error.status_code in {408, 409, 429} or error.status_code >= 500


def _model_retry_delay(error: Exception, attempt: int) -> float | None:
    from openai import APIStatusError

    delay = None
    if isinstance(error, APIStatusError):
        headers = error.response.headers
        try:
            delay = float(headers["retry-after-ms"]) / 1000
        except (KeyError, ValueError):
            value = headers.get("retry-after")
            try:
                delay = float(value)
            except (TypeError, ValueError):
                try:
                    parsed = email.utils.parsedate_tz(value) if value else None
                    if parsed is not None:
                        delay = email.utils.mktime_tz(parsed) - time.time()
                except (OverflowError, ValueError):
                    pass
    if delay is not None and math.isfinite(delay) and delay > 0:
        return delay if delay <= 60 else None
    return min(0.5 * 2 ** min(attempt - 1, 4), 8) * random.uniform(0.75, 1)


class _BoundedResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream: httpx.AsyncByteStream, limit: int):
        self.stream = stream
        self.limit = limit

    async def __aiter__(self):
        size = 0
        async for part in self.stream:
            size += len(part)
            if size > self.limit:
                raise ValueError("Provider response exceeds its read budget")
            yield part

    async def aclose(self):
        await self.stream.aclose()


def _redact_provider_metadata(value: Any) -> Any:
    if isinstance(value, str):
        match = _IMAGE_DATA_URL_RE.match(value)
        if match:
            return f"[image-data mime={match.group(1).lower()} encoded_chars={len(match.group(2))}]"
        return redact_provider_response(value)
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if key in _REDACTED_PROVIDER_KEYS:
                redacted[key] = "[redacted]"
            else:
                redacted[key] = _redact_provider_metadata(item)
        return redacted
    if isinstance(value, list):
        return [_redact_provider_metadata(item) for item in value]
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
        thought_signature = function_extra.get("thought_signature") or function_extra.get("thoughtSignature")
        if thought_signature is not None:
            metadata["thought_signature"] = thought_signature
    return metadata


class LLMProvider(Protocol):
    name: str

    async def chat(  # noqa
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        model: str,
        stream: bool = False,
        metadata: dict | None = None,
        stream_callback: Callable[[str], None] | None = None,
    ) -> LLMResult: ...  # noqa


class LLMProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> LLMProvider:
        return self._providers[name]


class UnconfiguredLLMProvider:
    name = "unconfigured"
    api_key = None
    base_url = None

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
        message = "No LLM provider configured. Set llm_provider in ~/.dojo/agents.yaml " "or configure a model in the dashboard settings."
        if stream and stream_callback:
            await emit_stream_delta(stream_callback, message)
        return LLMResult(content=message, metadata={"provider": self.name, "live": False, "error": "no_provider"})


class StaticLLMProvider:
    name = "static"

    def __init__(self, results: list[LLMResult] | None = None) -> None:
        self._results = list(results or [LLMResult(content="")])
        self.calls: list[dict[str, Any]] = []

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
        self.calls.append(
            {
                "messages": list(messages),
                "tools": list(tools),
                "model": model,
                "stream": stream,
                "metadata": metadata or {},
            }
        )
        if len(self._results) > 1:
            res = self._results.pop(0)
        else:
            res = self._results[0]

        if stream and stream_callback and res.content:
            chunk_size = 5
            for i in range(0, len(res.content), chunk_size):
                await emit_stream_delta(stream_callback, res.content[i : i + chunk_size])
        return res


class OpenAICompatibleProvider:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        author: str | None = None,
        extra_headers: dict[str, str] | None = None,
        max_retries: int | None = None,
        timeout: float | None = None,
        max_response_bytes: int | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.author = author
        self.extra_headers = dict(extra_headers or {})
        if max_retries is not None and (type(max_retries) is not int or max_retries < 0):
            raise ValueError("max_retries must be a nonnegative integer")
        if timeout is not None and (not math.isfinite(timeout) or timeout <= 0):
            raise ValueError("timeout must be finite and positive")
        if max_response_bytes is not None and (type(max_response_bytes) is not int or max_response_bytes <= 0):
            raise ValueError("max_response_bytes must be a positive integer")
        self.max_retries = 5 if max_retries is None else max_retries
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes

    async def _request_with_retries(self, client, create_kwargs, context, *, raw=False):
        create = client.chat.completions.with_raw_response.create if raw else client.chat.completions.create
        for attempt in range(1, self.max_retries + 2):
            context["attempt"] = attempt
            for key in ("http_status", "error_type", "retryable", "retry_exhausted"):
                context.pop(key, None)
            started = time.perf_counter()
            _log_model_request("llm_request_attempt", context)
            try:
                response = await create(**create_kwargs)
            except Exception as exc:
                retryable = _retryable_model_error(exc)
                context.update(
                    error_type=type(exc).__name__,
                    http_status=getattr(exc, "status_code", None),
                    retryable=retryable,
                    retry_exhausted=retryable and attempt > self.max_retries,
                )
                if not retryable or attempt > self.max_retries:
                    raise
                delay = _model_retry_delay(exc, attempt)
                if delay is None:
                    context.update(retryable=False, stop_reason="retry_after_exceeds_limit")
                    raise
                _log_model_request(
                    "llm_request_retry",
                    context,
                    level=logging.WARNING,
                    next_attempt=attempt + 1,
                    retry_delay_seconds=delay,
                    attempt_elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
                )
                await anyio.sleep(delay)
            else:
                status = getattr(response, "status_code", None)
                context["http_status"] = status if type(status) is int else 200
                _log_model_request("llm_request_response", context, attempt_elapsed_ms=round((time.perf_counter() - started) * 1000, 1))
                return response

    async def _raw_completion(self, client, create_kwargs, request_context) -> LLMResult:
        from openai import APIStatusError

        try:
            raw = await self._request_with_retries(client, create_kwargs, request_context, raw=True)
            response = raw.http_response
        except APIStatusError as exc:
            response = exc.response
        text = response.content.decode("utf-8", errors="backslashreplace")
        try:
            body = json.loads(
                text,
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
            )
        except (ValueError, RecursionError):
            body = {"_unparsed_response": text}
        body = redact_provider_response(body, self.api_key or "")
        choices = body.get("choices") if isinstance(body, dict) else None
        first = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        message = first.get("message") or {}
        content = message.get("content") if isinstance(message, dict) else None
        metadata = {
            "provider": self.name,
            "raw_response": {"http_status": response.status_code, "response": body},
            "finish_reason": first.get("finish_reason"),
        }
        if isinstance(body, dict) and isinstance(body.get("usage"), dict):
            metadata["usage"] = body["usage"]
        return LLMResult(
            content=content if isinstance(content, str) else "",
            metadata=metadata,
        )

    @staticmethod
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
            "total_tokens": int(total if total is not None else prompt_i + completion_i),
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

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        model: str,
        stream: bool = False,
        metadata: dict | None = None,
        stream_callback: Callable[[str], None] | None = None,
        request_options: dict[str, Any] | None = None,
        include_raw_response: bool = False,
    ) -> LLMResult:
        if include_raw_response and stream:
            raise ValueError("Raw receipts require a non-streaming call")
        options = dict(request_options or {})
        allowed = {
            "temperature",
            "max_completion_tokens",
            "max_tokens",
            "response_format",
            "extra_body",
        }
        if set(options) - allowed:
            raise ValueError("Unsupported chat request options")
        extra_body = {
            **((metadata or {}).get("_dojo_extra_body") or {}),
            **(options.get("extra_body") or {}),
        }
        if set(extra_body) & {"model", "messages", "tools", "stream"}:
            raise ValueError("extra_body cannot override the chat request identity")
        if extra_body:
            options["extra_body"] = extra_body
        if "max_completion_tokens" in options:
            options["extra_body"] = {
                **extra_body,
                "max_completion_tokens": options.pop("max_completion_tokens"),
            }
        if not self.api_key:
            return LLMResult(
                content=("OpenAI-compatible provider is configured without an API key. " "Set the configured api_key_env before making live calls."),
                metadata={"provider": self.name, "live": False},
            )
        from openai import AsyncOpenAI

        client_options: dict[str, Any] = {"max_retries": 0}
        if self.timeout is not None:
            client_options["timeout"] = self.timeout
        if self.max_response_bytes is not None:

            async def bound_response(response):
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise ValueError("Bounded provider responses must use identity encoding")
                if response.is_stream_consumed and len(response.content) > self.max_response_bytes:
                    raise ValueError("Provider response exceeds its read budget")
                response.stream = _BoundedResponseStream(response.stream, self.max_response_bytes)

            client_options["http_client"] = httpx.AsyncClient(
                event_hooks={"response": [bound_response]},
                headers={"Accept-Encoding": "identity"},
                follow_redirects=False,
                trust_env=False,
            )
        client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            default_headers=self.extra_headers or None,
            **client_options,
        )

        actual_model = model
        is_model_router = self.name == "model-router" or "openrouter.ai" in str(self.base_url or "").lower() or "orcarouter.ai" in str(self.base_url or "").lower()
        if is_model_router and self.author and not model.startswith(f"{self.author}/"):
            actual_model = f"{self.author}/{model}"

        request_context = {
            "call_id": "llm-" + uuid.uuid4().hex,
            "provider": self.name,
            "model": actual_model,
            "run_id": current_run_id(),
            "session_id": getattr((metadata or {}).get("_dojo_request"), "session_id", "") or (metadata or {}).get("session_id", ""),
            "max_attempts": self.max_retries + 1,
            "attempt": 0,
            "stream_opened": False,
        }
        outcome = "failed"
        call_started = time.perf_counter()
        try:
            request_started = time.perf_counter()
            request_started_wall = time.time()
            try:
                create_kwargs: dict[str, Any] = {
                    "model": actual_model,
                    "messages": messages,
                    "tools": [{"type": "function", "function": tool} for tool in tools] or None,
                    "stream": stream,
                }
                if stream:
                    create_kwargs["stream_options"] = {"include_usage": True}
                create_kwargs.update(options)
                if include_raw_response:
                    result = await self._raw_completion(client, create_kwargs, request_context)
                    outcome = "succeeded" if result.metadata["raw_response"]["http_status"] < 400 else "failed"
                    return result
                response = await self._request_with_retries(client, create_kwargs, request_context)
                request_context["stream_opened"] = stream
            except Exception as e:
                err_msg = str(e)
                max_context, requested = parse_context_length_error(err_msg)
                if max_context is not None or requested is not None:
                    LOGGER.warning(
                        "Context length exceeded for model %s: max=%s requested=%s",
                        model,
                        max_context,
                        requested,
                    )
                    raise ContextLengthExceededError(
                        err_msg,
                        max_context=max_context,
                        requested_tokens=requested,
                    ) from e
                raise

            if stream and stream_callback:
                full_content = []
                full_reasoning = []
                tool_calls_buffer: dict[int, dict[str, Any]] = {}
                stream_usage: dict[str, int] | None = None
                event_sink = (metadata or {}).get("_dojo_event_sink")
                reasoning_started = False
                reasoning_ended = False
                content_started = False
                coalesce = getattr((metadata or {}).get("_dojo_request"), "channel", None) == "job"
                pending_reasoning: list[str] = []
                pending_text: list[str] = []
                reasoning_chars = text_chars = 0
                last_reasoning_flush = last_text_flush = time.monotonic()
                # Stream timing markers must exist before the loop: they are read on
                # every chunk, so a missing initializer raises UnboundLocalError.
                first_chunk_at: float | None = None
                first_content_at: float | None = None
                last_chunk_at: float | None = None

                async def flush_reasoning() -> None:
                    nonlocal reasoning_chars, last_reasoning_flush
                    if pending_reasoning:
                        await event_sink.wait_for_capacity()
                        event_sink.thinking_delta("".join(pending_reasoning))
                        pending_reasoning.clear()
                        reasoning_chars = 0
                        last_reasoning_flush = time.monotonic()

                async def flush_text() -> None:
                    nonlocal text_chars, last_text_flush
                    if pending_text:
                        await emit_stream_delta(stream_callback, "".join(pending_text))
                        pending_text.clear()
                        text_chars = 0
                        last_text_flush = time.monotonic()

                async for chunk in response:
                    chunk_usage = self._usage_dict(getattr(chunk, "usage", None))
                    if chunk_usage is not None:
                        stream_usage = chunk_usage
                    if not chunk.choices:
                        continue
                    last_chunk_at = time.perf_counter()
                    if first_chunk_at is None:
                        # Reasoning chunks count as the first token: users still wait
                        # for them, and providers bill them.
                        first_chunk_at = last_chunk_at
                    choice = chunk.choices[0]
                    delta = choice.delta
                    if event_sink is not None:
                        await event_sink.wait_for_capacity()
                    reasoning_delta = getattr(delta, "reasoning_content", None) or (
                        delta.model_extra.get("reasoning_content") if hasattr(delta, "model_extra") and delta.model_extra else None
                    )
                    if reasoning_delta:
                        full_reasoning.append(reasoning_delta)
                        if event_sink is not None and not content_started:
                            if not reasoning_started:
                                event_sink.thinking_start()
                                reasoning_started = True
                            if coalesce:
                                pending_reasoning.append(reasoning_delta)
                                reasoning_chars += len(reasoning_delta)
                                if reasoning_chars >= 1024 or time.monotonic() - last_reasoning_flush >= 0.05:
                                    await flush_reasoning()
                            else:
                                event_sink.thinking_delta(reasoning_delta)
                    content_delta = delta.content or ""
                    if content_delta:
                        if first_content_at is None:
                            first_content_at = time.perf_counter()
                        if event_sink is not None and reasoning_started and not reasoning_ended:
                            await flush_reasoning()
                            event_sink.thinking_end()
                            reasoning_ended = True
                        content_started = True
                        full_content.append(content_delta)
                        if coalesce:
                            pending_text.append(content_delta)
                            text_chars += len(content_delta)
                            if text_chars >= 1024 or time.monotonic() - last_text_flush >= 0.05:
                                await flush_text()
                        else:
                            await emit_stream_delta(stream_callback, content_delta)
                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            if idx not in tool_calls_buffer:
                                tool_calls_buffer[idx] = {"id": "", "name": "", "arguments": "", "metadata": {}}
                            if tc_delta.id:
                                tool_calls_buffer[idx]["id"] = tc_delta.id
                            if tc_delta.function and tc_delta.function.name:
                                tool_calls_buffer[idx]["name"] = tc_delta.function.name
                            if tc_delta.function and tc_delta.function.arguments:
                                tool_calls_buffer[idx]["arguments"] += tc_delta.function.arguments
                            tool_calls_buffer[idx]["metadata"].update(_extract_tool_call_metadata(tc_delta, self.name))

                await flush_reasoning()
                await flush_text()
                if event_sink is not None and reasoning_started and not reasoning_ended:
                    await event_sink.wait_for_capacity()
                    event_sink.thinking_end()
                    reasoning_ended = True
                final_tool_calls = []
                for idx, tc in sorted(tool_calls_buffer.items()):
                    args_dict = {}
                    if tc["arguments"].strip():
                        try:
                            args_dict = json.loads(tc["arguments"])
                        except json.JSONDecodeError:
                            args_dict = {"raw_arguments": tc["arguments"]}
                    final_tool_calls.append(ToolCall(id=tc["id"], name=tc["name"], arguments=args_dict, metadata=dict(tc["metadata"])))
                metadata: dict[str, Any] = {
                    "provider": self.name,
                    "reasoning_content": "".join(full_reasoning),
                    # Prevent the Strands bridge from replaying final reasoning
                    # after streamed answer deltas.
                    "reasoning_streamed": bool(full_reasoning),
                }
                if stream_usage is not None:
                    metadata["usage"] = stream_usage
                else:
                    metadata["usage_available"] = False
                # Timing no longer rides a private metadata channel; the framework
                # emits a neutral LLMCallEvent instead and the host persists it.
                stream_ended = time.perf_counter()
                timing: dict[str, int] = {"request_ms": int((stream_ended - request_started) * 1000)}
                if first_chunk_at is not None:
                    timing["ttft_ms"] = int((first_chunk_at - request_started) * 1000)
                if first_content_at is not None:
                    timing["ttfc_ms"] = int((first_content_at - request_started) * 1000)
                if first_chunk_at is not None and last_chunk_at is not None:
                    timing["decode_ms"] = int((last_chunk_at - first_chunk_at) * 1000)
                # Framework-neutral telemetry event; the host decides how to persist
                # it. run_id comes from the run-scoped context (see telemetry.py).
                emit(
                    LLMCallEvent(
                        run_id=current_run_id(),
                        model=actual_model,
                        provider=self.name,
                        started_at=request_started_wall,
                        request_ms=timing.get("request_ms", 0),
                        ttft_ms=timing.get("ttft_ms"),
                        ttfc_ms=timing.get("ttfc_ms"),
                        decode_ms=timing.get("decode_ms"),
                        usage=stream_usage,
                        status="succeeded",
                    )
                )
                outcome = "succeeded"
                return LLMResult(
                    content="".join(full_content),
                    tool_calls=final_tool_calls,
                    metadata=metadata,
                )
            else:
                message = response.choices[0].message
                reasoning_content = getattr(message, "reasoning_content", None) or (
                    message.model_extra.get("reasoning_content") if hasattr(message, "model_extra") and message.model_extra else None
                )
                final_tool_calls = []
                if message.tool_calls:
                    for tc in message.tool_calls:
                        args_dict = {}
                        if tc.function.arguments:
                            try:
                                args_dict = json.loads(tc.function.arguments)
                            except json.JSONDecodeError:
                                args_dict = {"raw_arguments": tc.function.arguments}
                        final_tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args_dict, metadata=_extract_tool_call_metadata(tc, self.name)))
                result_metadata: dict[str, Any] = {
                    "provider": self.name,
                    "reasoning_content": reasoning_content or "",
                }
                usage_dict = self._usage_dict(getattr(response, "usage", None))
                if usage_dict is not None:
                    result_metadata["usage"] = usage_dict
                else:
                    result_metadata["usage_available"] = False
                emit(
                    LLMCallEvent(
                        run_id=current_run_id(),
                        model=actual_model,
                        provider=self.name,
                        started_at=request_started_wall,
                        request_ms=max(0, int((time.perf_counter() - request_started) * 1000)),
                        usage=usage_dict,
                        status="succeeded",
                    )
                )
                outcome = "succeeded"
                return LLMResult(
                    content=message.content or "",
                    tool_calls=final_tool_calls,
                    metadata=result_metadata,
                )
        except BaseException as exc:
            outcome = "cancelled" if isinstance(exc, anyio.get_cancelled_exc_class()) else "failed"
            request_context["error_type"] = type(exc).__name__
            raise
        finally:
            _log_model_request(
                "llm_request_end",
                request_context,
                level=logging.INFO if outcome == "succeeded" else logging.WARNING,
                outcome=outcome,
                elapsed_ms=round((time.perf_counter() - call_started) * 1000, 1),
            )
            with anyio.move_on_after(5, shield=True):
                try:
                    await client.close()
                except Exception as exc:
                    LOGGER.warning("llm_client_close_failed error_type=%s", type(exc).__name__)


def get_strands_model(provider_name: str, config: Any) -> Any:
    """Factory to load strands models natively."""
    import os
    from strands.models.openai import OpenAIModel
    from strands.models.gemini import GeminiModel
    from strands.models.bedrock import BedrockModel
    from strands.models.anthropic import AnthropicModel
    from strands.models.ollama import OllamaModel

    provider_name = provider_name.lower()

    if isinstance(config, dict):
        api_key = config.get("api_key")
        api_key_env = config.get("api_key_env")
        base_url = config.get("base_url")
        model = config.get("model")
        extra_headers = config.get("extra_headers") or {}
        max_retries = config.get("max_retries", 5)
    else:
        api_key = getattr(config, "api_key", None)
        api_key_env = getattr(config, "api_key_env", None)
        base_url = getattr(config, "base_url", None)
        model = getattr(config, "model", None)
        extra_headers = getattr(config, "extra_headers", {}) or {}
        max_retries = getattr(config, "max_retries", 5)

    if not api_key and api_key_env:
        api_key = os.getenv(api_key_env)

    # 1. OpenAI, DeepSeek, Qwen, Moonshot, etc.
    if provider_name == "openai":
        return OpenAIModel(
            client_args={
                "api_key": api_key,
                "base_url": base_url,
                "default_headers": extra_headers or None,
                "max_retries": max_retries,
            },
            model_id=model or "gpt-4o",
        )
    elif provider_name == "deepseek":
        return OpenAIModel(
            client_args={
                "api_key": api_key,
                "base_url": base_url or "https://api.deepseek.com",
                "default_headers": extra_headers or None,
                "max_retries": max_retries,
            },
            model_id=model or "deepseek-chat",
        )
    elif provider_name in ("qwen", "dashscope"):
        return OpenAIModel(
            client_args={
                "api_key": api_key,
                "base_url": base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "default_headers": extra_headers or None,
                "max_retries": max_retries,
            },
            model_id=model or "qwen-max",
        )
    elif provider_name in ("kimi", "moonshot"):
        return OpenAIModel(
            client_args={
                "api_key": api_key,
                "base_url": base_url or "https://api.moonshot.cn/v1",
                "default_headers": extra_headers or None,
                "max_retries": max_retries,
            },
            model_id=model or "moonshot-v1-8k",
        )
    elif provider_name in ("glm", "zhipu", "zhipuai"):
        return OpenAIModel(
            client_args={
                "api_key": api_key,
                "base_url": base_url or "https://open.bigmodel.cn/api/paas/v4/",
                "default_headers": extra_headers or None,
                "max_retries": max_retries,
            },
            model_id=model or "glm-4",
        )
    elif provider_name == "minimax":
        return OpenAIModel(
            client_args={
                "api_key": api_key,
                "base_url": base_url or "https://api.minimax.chat/v1",
                "default_headers": extra_headers or None,
                "max_retries": max_retries,
            },
            model_id=model or "abab6.5-chat",
        )
    # 2. Gemini
    elif provider_name == "gemini":
        return GeminiModel(client_args={"api_key": api_key}, model_id=model or "gemini-2.5-flash")
    # 3. Anthropic
    elif provider_name == "anthropic":
        return AnthropicModel(api_key=api_key, model_id=model or "claude-3-5-sonnet")
    # 4. Bedrock
    elif provider_name == "bedrock":
        return BedrockModel(model_id=model or "us.amazon.nova-pro-v1:0")
    # 5. Ollama
    elif provider_name == "ollama":
        return OllamaModel(host=base_url or "http://localhost:11434", model_id=model or "llama3")
    else:
        raise ValueError(f"Unsupported model provider: {provider_name}")
