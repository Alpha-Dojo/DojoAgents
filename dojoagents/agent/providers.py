from typing import Any, Callable, Protocol

from dojoagents.agent.context_length import ContextLengthExceededError, parse_context_length_error
from dojoagents.agent.models import LLMResult
from dojoagents.agent.provider_contracts import (
    OPENAI_COMPATIBLE_DEFAULT,
    OpenAIRequestPolicy,
    ProviderRequest,
)
from dojoagents.agent.provider_request import OpenAIRequestAdapter
from dojoagents.agent.provider_profiles import ModelIdPolicy
from dojoagents.agent.provider_response import (
    OpenAIResponseAdapter,
    redact_provider_metadata as _redact_provider_metadata,
    redact_provider_response,
)
from dojoagents.agent.provider_transport import OpenAITransport
from dojoagents.logging import LOGGER


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
            stream_callback(message)
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
                stream_callback(res.content[i : i + chunk_size])
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
        request_policy: OpenAIRequestPolicy = OPENAI_COMPATIBLE_DEFAULT,
        model_id_policy: ModelIdPolicy = ModelIdPolicy.AS_IS,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.author = author
        self.extra_headers = dict(extra_headers or {})
        self.max_retries = max_retries
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes
        self.request_adapter = OpenAIRequestAdapter(
            request_policy,
            author=author,
            model_id_policy=model_id_policy,
        )
        self.transport = OpenAITransport(
            api_key=api_key or "",
            base_url=base_url,
            extra_headers=self.extra_headers,
            max_retries=max_retries,
            timeout=timeout,
            max_response_bytes=max_response_bytes,
        )
        self.response_adapter = OpenAIResponseAdapter()

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
        request = ProviderRequest(
            model=model,
            messages=tuple(dict(message) for message in messages),
            tools=tuple(dict(tool) for tool in tools),
            stream=stream,
            metadata=dict(metadata or {}),
            options=dict(request_options or {}),
        )
        create_kwargs = self.request_adapter.build(request)
        if not self.api_key:
            return LLMResult(
                content=("OpenAI-compatible provider is configured without an API key. " "Set the configured api_key_env before making live calls."),
                metadata={"provider": self.name, "live": False},
            )
        try:
            response = await self.transport.send(
                create_kwargs,
                include_raw_response=include_raw_response,
            )
            return await self.response_adapter.decode(
                response,
                provider_name=self.name,
                api_key=self.api_key or "",
                metadata=metadata,
                stream_callback=stream_callback,
            )
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
            LOGGER.exception(
                "Error calling OpenAI API: %s, messages: %s, tools: %s, model: %s",
                redact_provider_response(str(e), self.api_key or ""),
                _redact_provider_metadata(create_kwargs.get("messages", [])),
                _redact_provider_metadata(create_kwargs.get("tools", [])),
                create_kwargs["model"],
            )
            raise e
