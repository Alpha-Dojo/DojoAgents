from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ProviderRequest:
    """Provider-neutral snapshot of one outbound LLM request.

    The outbound adapter deep-copies the internal message and tool mappings so
    wire transformations cannot mutate session state through nested objects.
    """

    model: str
    messages: tuple[dict[str, Any], ...]
    tools: tuple[dict[str, Any], ...] = ()
    stream: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OpenAIRequestPolicy:
    """Deterministic wire choices for an OpenAI-compatible endpoint."""

    message_name_policy: Literal["preserve", "omit"] = "omit"
    empty_tools_policy: Literal["omit", "empty_array"] = "omit"
    stream_usage_policy: Literal["include", "unsupported"] = "include"


OPENAI_COMPATIBLE_DEFAULT = OpenAIRequestPolicy()
