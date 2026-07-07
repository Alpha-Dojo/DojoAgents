import copy
from typing import Any, Callable

from dojoagents.agent.models import LLMResult, ToolCall
from dojoagents.agent.providers import OpenAICompatibleProvider
from dojoagents.logging import get_logger

LOGGER = get_logger(__name__)


class MoonshotProvider(OpenAICompatibleProvider):
    name = "moonshot"

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None, thinking: bool = True) -> None:
        super().__init__(api_key=api_key, base_url=base_url)
        self.thinking = thinking

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
        """
        Overrides OpenAICompatibleProvider.chat to handle Moonshot's specific requirements:
        1. Inject `reasoning_content` from Dojo's history into the assistant messages in a format expected by the API or as part of content.
        2. Append thinking=True to create_kwargs or handle temperature constraints.
        """
        # For Kimi (Moonshot), if thinking is enabled, they recommend temperature=1.0.
        # Otherwise, temperature=0.6.
        temperature = 1.0 if self.thinking else 0.6

        # Deep copy to avoid mutating the shared message history
        processed_messages = copy.deepcopy(messages)

        # Moonshot typically supports a reasoning_content field in the assistant message, or expects us to pass it.
        # Since standard OpenAI ChatCompletionMessageParam may drop unknown fields depending on the SDK,
        # but the latest versions allow extra kwargs, we simply ensure `reasoning_content` is attached to assistant messages
        # if it was saved as `reasoning` or `reasoning_content` in Dojo's internal representation.
        # Note: In loop.py, strands_to_dojo_messages maps reasoning to `msg["reasoning_content"]`.
        for msg in processed_messages:
            if msg.get("role") == "assistant" and "reasoning_content" in msg:
                # Kimi API typically accepts "reasoning_content" or equivalent at the message level
                # if it generated it. We preserve it exactly as requested.
                pass

        if not self.api_key:
            return LLMResult(
                content="Moonshot provider is configured without an API key.",
                metadata={"provider": self.name, "live": False},
            )

        from openai import AsyncOpenAI
        from dojoagents.agent.context_length import ContextLengthExceededError, parse_context_length_error
        from dojoagents.agent.providers import _extract_tool_call_metadata

        # Moonshot API base url is typically https://api.moonshot.cn/v1
        client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url or "https://api.moonshot.cn/v1")

        try:
            create_kwargs: dict[str, Any] = {
                "model": model,
                "messages": processed_messages,
                "temperature": temperature,
                "stream": stream,
            }
            if tools:
                create_kwargs["tools"] = [{"type": "function", "function": tool} for tool in tools]

            # In some SDK configurations, sending unknown kwargs might cause errors, but Moonshot's OpenAI-compatible endpoint
            # might not support `thinking` parameter in the completions call if it's strictly openai sdk,
            # or it might require it. Wait, langchain-moonshot uses the Kimi specific client or passes `extra_body`.
            # Let's pass extra_body for custom fields to bypass OpenAI SDK strict pydantic validation if any.
            # But the OpenAI SDK allows unknown kwargs at the top level in some versions. To be safe, we use extra_body.
            # Moonshot's docs often suggest passing custom parameters or using the specific Kimi client.
            # Actually, Kimi doesn't have a `thinking` param at the /chat/completions root in the official docs, it's often implied by model name (like kimi-k2.5).
            # Wait, the planning doc explicitly mentions Moonshot provides `thinking=True/False`.
            # We'll pass it in `extra_body` to be safe against openai SDK validation.
            if self.thinking:
                create_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
            else:
                create_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

            if stream:
                create_kwargs["stream_options"] = {"include_usage": True}

            response = await client.chat.completions.create(**create_kwargs)
        except Exception as e:
            err_msg = str(e)
            max_context, requested = parse_context_length_error(err_msg)
            if max_context is not None or requested is not None:
                LOGGER.warning("Context length exceeded for model %s: max=%s requested=%s", model, max_context, requested)
                raise ContextLengthExceededError(err_msg, max_context=max_context, requested_tokens=requested) from e
            LOGGER.exception("Error calling Moonshot API: %s", e)
            raise e

        # Stream handling is very similar to OpenAICompatibleProvider
        if stream and stream_callback:
            full_content = []
            full_reasoning = []
            tool_calls_buffer: dict[int, dict[str, Any]] = {}
            stream_usage: dict[str, int] | None = None
            try:
                async for chunk in response:
                    chunk_usage = self._usage_dict(getattr(chunk, "usage", None))
                    if chunk_usage is not None:
                        stream_usage = chunk_usage

                    if not chunk.choices:
                        continue

                    choice = chunk.choices[0]
                    delta = choice.delta

                    # Extract reasoning
                    reasoning_delta = getattr(delta, "reasoning_content", None) or (
                        delta.model_extra.get("reasoning_content") if hasattr(delta, "model_extra") and delta.model_extra else None
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
                                tool_calls_buffer[idx] = {"id": "", "name": "", "arguments": "", "metadata": {}}
                            if tc_delta.id:
                                tool_calls_buffer[idx]["id"] = tc_delta.id
                            if tc_delta.function and tc_delta.function.name:
                                tool_calls_buffer[idx]["name"] = tc_delta.function.name
                            if tc_delta.function and tc_delta.function.arguments:
                                tool_calls_buffer[idx]["arguments"] += tc_delta.function.arguments
                            tool_calls_buffer[idx]["metadata"].update(_extract_tool_call_metadata(tc_delta, self.name))

                final_tool_calls = []
                for idx, tc in sorted(tool_calls_buffer.items()):
                    args_dict = {}
                    import json

                    try:
                        args_dict = json.loads(tc["arguments"])
                    except Exception as e:
                        LOGGER.warning("Failed to parse tool call arguments from Moonshot: %s (err: %s)", tc["arguments"], e)
                    final_tool_calls.append(
                        ToolCall(
                            id=tc["id"],
                            name=tc["name"],
                            arguments=args_dict,
                            metadata=tc["metadata"],
                        )
                    )

                return LLMResult(
                    content="".join(full_content),
                    tool_calls=final_tool_calls,
                    metadata={
                        "provider": self.name,
                        "model": model,
                        "usage": stream_usage,
                        "reasoning_content": "".join(full_reasoning),
                    },
                )
            except Exception as e:
                LOGGER.exception(f"Error streaming Moonshot API: {e}")
                raise e
        else:
            # Non-streaming
            choice = response.choices[0]
            msg = choice.message

            reasoning_content = getattr(msg, "reasoning_content", None) or (msg.model_extra.get("reasoning_content") if hasattr(msg, "model_extra") and msg.model_extra else None)

            final_tool_calls = []
            if msg.tool_calls:
                import json

                for tc in msg.tool_calls:
                    args_dict = {}
                    try:
                        args_dict = json.loads(tc.function.arguments)
                    except Exception as e:
                        LOGGER.warning("Failed to parse tool call arguments from Moonshot: %s (err: %s)", tc.function.arguments, e)
                    final_tool_calls.append(
                        ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            arguments=args_dict,
                            metadata=_extract_tool_call_metadata(tc, self.name),
                        )
                    )

            return LLMResult(
                content=msg.content or "",
                tool_calls=final_tool_calls,
                metadata={
                    "provider": self.name,
                    "model": model,
                    "usage": self._usage_dict(getattr(response, "usage", None)),
                    "reasoning_content": reasoning_content or "",
                },
            )
