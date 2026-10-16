from __future__ import annotations

import inspect
import math
from dataclasses import dataclass, field
from typing import Any

import anyio
import httpx

from dojoagents.logging import get_logger


_CLIENT_CLOSE_TIMEOUT_SECONDS = 5.0
LOGGER = get_logger(__name__)


class _BoundedResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream: httpx.AsyncByteStream, limit: int) -> None:
        self.stream = stream
        self.limit = limit

    async def __aiter__(self):
        size = 0
        async for part in self.stream:
            size += len(part)
            if size > self.limit:
                raise ValueError("Provider response exceeds its read budget")
            yield part

    async def aclose(self) -> None:
        await self.stream.aclose()


async def _close_if_supported(value: Any) -> None:
    closer = getattr(value, "aclose", None)
    if closer is None:
        closer = getattr(value, "close", None)
    if closer is None:
        return
    result = closer()
    if inspect.isawaitable(result):
        await result


async def _close_with_timeout(value: Any, *, label: str) -> None:
    with anyio.move_on_after(_CLIENT_CLOSE_TIMEOUT_SECONDS) as scope:
        try:
            await _close_if_supported(value)
        except Exception:
            LOGGER.exception("Failed to close OpenAI transport %s", label)
    if scope.cancel_called:
        LOGGER.warning(
            "Timed out closing OpenAI transport %s after %ss",
            label,
            _CLIENT_CLOSE_TIMEOUT_SECONDS,
        )


@dataclass
class OpenAITransportResponse:
    """A response whose OpenAI client remains alive until decoding completes."""

    value: Any
    client: Any
    is_stream: bool = False
    is_raw: bool = False
    _closed: bool = field(default=False, init=False)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        with anyio.CancelScope(shield=True):
            if self.is_stream or self.is_raw:
                await _close_with_timeout(self.value, label="response")
            await _close_with_timeout(self.client, label="client")

    async def __aenter__(self) -> OpenAITransportResponse:
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback) -> None:
        await self.aclose()


class OpenAITransport:
    """Own the OpenAI SDK client, HTTP limits, and response lifecycle."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        extra_headers: dict[str, str] | None = None,
        max_retries: int | None = None,
        timeout: float | None = None,
        max_response_bytes: int | None = None,
    ) -> None:
        if max_retries is not None and (
            type(max_retries) is not int or max_retries < 0
        ):
            raise ValueError("max_retries must be a nonnegative integer")
        if timeout is not None and (not math.isfinite(timeout) or timeout <= 0):
            raise ValueError("timeout must be finite and positive")
        if max_response_bytes is not None and (
            type(max_response_bytes) is not int or max_response_bytes <= 0
        ):
            raise ValueError("max_response_bytes must be a positive integer")

        self.api_key = api_key
        self.base_url = base_url
        self.extra_headers = dict(extra_headers or {})
        self.max_retries = max_retries
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes

    def _client_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {}
        if self.max_retries is not None:
            options["max_retries"] = self.max_retries
        if self.timeout is not None:
            options["timeout"] = self.timeout
        if self.max_response_bytes is not None:
            limit = self.max_response_bytes

            async def bound_response(response: httpx.Response) -> None:
                if response.headers.get(
                    "Content-Encoding",
                    "identity",
                ).lower() != "identity":
                    raise ValueError(
                        "Bounded provider responses must use identity encoding"
                    )
                if response.is_stream_consumed and len(response.content) > limit:
                    raise ValueError("Provider response exceeds its read budget")
                response.stream = _BoundedResponseStream(response.stream, limit)

            options["http_client"] = httpx.AsyncClient(
                event_hooks={"response": [bound_response]},
                headers={"Accept-Encoding": "identity"},
                follow_redirects=False,
                trust_env=False,
            )
        return options

    async def _build_client(self) -> Any:
        from openai import AsyncOpenAI

        options = self._client_options()
        try:
            return AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                default_headers=self.extra_headers or None,
                **options,
            )
        except BaseException:
            http_client = options.get("http_client")
            if http_client is not None:
                with anyio.CancelScope(shield=True):
                    await _close_with_timeout(http_client, label="HTTP client")
            raise

    @staticmethod
    def _supports_direct_max_completion_tokens(create: Any) -> bool:
        try:
            parameters = inspect.signature(create).parameters.values()
        except (TypeError, ValueError):
            return True
        return any(
            parameter.name == "max_completion_tokens"
            or parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters
        )

    def _encode_sdk_payload(self, payload: dict[str, Any], create: Any) -> dict[str, Any]:
        """Map logical request fields onto the installed OpenAI SDK surface."""

        encoded = dict(payload)
        extra_body = dict(encoded.get("extra_body") or {})
        if "max_completion_tokens" in encoded:
            # The logical first-class field always wins over a duplicate value
            # smuggled through extra_body.  OpenAI SDK versions merge these two
            # mappings in different places, so leaving the duplicate would make
            # the wire value depend on the installed SDK version.
            extra_body.pop("max_completion_tokens", None)
            if not self._supports_direct_max_completion_tokens(create):
                extra_body["max_completion_tokens"] = encoded.pop(
                    "max_completion_tokens"
                )
        if extra_body:
            encoded["extra_body"] = extra_body
        else:
            encoded.pop("extra_body", None)
        return encoded

    async def send(
        self,
        payload: dict[str, Any],
        *,
        include_raw_response: bool = False,
    ) -> OpenAITransportResponse:
        """Send once and transfer client ownership to the returned response."""

        client = await self._build_client()
        try:
            create = client.chat.completions.create
            encoded = self._encode_sdk_payload(payload, create)
            if include_raw_response:
                from openai import APIStatusError

                try:
                    raw = await client.chat.completions.with_raw_response.create(
                        **encoded
                    )
                    value = raw.http_response
                except APIStatusError as exc:
                    value = exc.response
                return OpenAITransportResponse(
                    value=value,
                    client=client,
                    is_raw=True,
                )

            value = await create(**encoded)
            return OpenAITransportResponse(
                value=value,
                client=client,
                is_stream=bool(encoded.get("stream")),
            )
        except BaseException:
            response = OpenAITransportResponse(value=None, client=client)
            await response.aclose()
            raise
