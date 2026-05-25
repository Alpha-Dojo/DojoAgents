from __future__ import annotations

from typing import Any, Protocol

from dojoagents.agent.models import LLMResult


class LLMProvider(Protocol):
    name: str

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
        ...


class LLMProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> LLMProvider:
        return self._providers[name]


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
                stream_callback(res.content[i:i+chunk_size])
        return res


class OpenAICompatibleProvider:
    name = "openai"

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url

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
                content=(
                    "OpenAI-compatible provider is configured without an API key. "
                    "Set the configured api_key_env before making live calls."
                ),
                metadata={"provider": self.name, "live": False},
            )
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=[{"type": "function", "function": tool} for tool in tools] or None,
            stream=stream,
        )
        if stream and stream_callback:
            full_content = []
            async for chunk in response:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    full_content.append(delta)
                    stream_callback(delta)
            return LLMResult(content="".join(full_content), metadata={"provider": self.name})
        else:
            message = response.choices[0].message
            return LLMResult(content=message.content or "", metadata={"provider": self.name})
