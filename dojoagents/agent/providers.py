import json
from typing import Any, Protocol, Callable

from dojoagents.agent.models import LLMResult, ToolCall


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
            full_reasoning = []
            tool_calls_buffer: dict[int, dict[str, Any]] = {}
            async for chunk in response:
                choice = chunk.choices[0]
                delta = choice.delta
                reasoning_delta = getattr(delta, "reasoning_content", None) or (
                    delta.model_extra.get("reasoning_content")
                    if hasattr(delta, "model_extra") and delta.model_extra
                    else None
                )
                if reasoning_delta:
                    full_reasoning.append(reasoning_delta)
                content_delta = delta.content or ""
                if content_delta:
                    full_content.append(content_delta)
                    stream_callback(content_delta)
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {
                                "id": "",
                                "name": "",
                                "arguments": ""
                            }
                        if tc_delta.id:
                            tool_calls_buffer[idx]["id"] = tc_delta.id
                        if tc_delta.function and tc_delta.function.name:
                            tool_calls_buffer[idx]["name"] = tc_delta.function.name
                        if tc_delta.function and tc_delta.function.arguments:
                            tool_calls_buffer[idx]["arguments"] += tc_delta.function.arguments

            final_tool_calls = []
            for idx, tc in sorted(tool_calls_buffer.items()):
                args_dict = {}
                if tc["arguments"].strip():
                    try:
                        args_dict = json.loads(tc["arguments"])
                    except json.JSONDecodeError:
                        args_dict = {"raw_arguments": tc["arguments"]}
                final_tool_calls.append(
                    ToolCall(
                        id=tc["id"],
                        name=tc["name"],
                        arguments=args_dict
                    )
                )
            return LLMResult(
                content="".join(full_content),
                tool_calls=final_tool_calls,
                metadata={
                    "provider": self.name,
                    "reasoning_content": "".join(full_reasoning),
                }
            )
        else:
            message = response.choices[0].message
            reasoning_content = getattr(message, "reasoning_content", None) or (
                message.model_extra.get("reasoning_content")
                if hasattr(message, "model_extra") and message.model_extra
                else None
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
                    final_tool_calls.append(
                        ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            arguments=args_dict
                        )
                    )
            return LLMResult(
                content=message.content or "",
                tool_calls=final_tool_calls,
                metadata={
                    "provider": self.name,
                    "reasoning_content": reasoning_content or "",
                }
            )
