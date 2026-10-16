from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from dojoagents.agent.provider_contracts import (
    OPENAI_COMPATIBLE_DEFAULT,
    OpenAIRequestPolicy,
    ProviderRequest,
)
from dojoagents.agent.provider_profiles import ModelIdPolicy


class OpenAIRequestAdapter:
    """Pure conversion from Dojo's internal request to OpenAI SDK arguments."""

    ALLOWED_OPTIONS = {
        "temperature",
        "max_completion_tokens",
        "max_tokens",
        "response_format",
        "extra_body",
    }
    IDENTITY_FIELDS = {"model", "messages", "tools", "stream"}

    def __init__(
        self,
        policy: OpenAIRequestPolicy = OPENAI_COMPATIBLE_DEFAULT,
        *,
        author: str | None = None,
        model_id_policy: ModelIdPolicy = ModelIdPolicy.AS_IS,
    ) -> None:
        self.policy = policy
        self.author = author
        self.model_id_policy = model_id_policy

    def _encode_message(self, message: dict[str, Any]) -> dict[str, Any]:
        encoded = deepcopy(message)
        if self.policy.message_name_policy == "omit":
            encoded.pop("name", None)
        return encoded

    def _encode_model(self, model: str) -> str:
        if (
            self.model_id_policy is ModelIdPolicy.AUTHOR_PREFIX
            and self.author
            and not model.startswith(f"{self.author}/")
        ):
            return f"{self.author}/{model}"
        return model

    @staticmethod
    def _mapping_option(value: Any, *, name: str) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise ValueError(f"{name} must be a mapping")
        return dict(value)

    def build(self, request: ProviderRequest) -> dict[str, Any]:
        """Build SDK arguments without mutating any request-owned mapping."""

        options = dict(request.options)
        if set(options) - self.ALLOWED_OPTIONS:
            raise ValueError("Unsupported chat request options")

        metadata_extra = self._mapping_option(
            request.metadata.get("_dojo_extra_body"),
            name="metadata._dojo_extra_body",
        )
        option_extra = self._mapping_option(
            options.pop("extra_body", None),
            name="request_options.extra_body",
        )
        extra_body = {**metadata_extra, **option_extra}
        if set(extra_body) & self.IDENTITY_FIELDS:
            raise ValueError("extra_body cannot override the chat request identity")

        payload: dict[str, Any] = {
            "model": self._encode_model(request.model),
            "messages": [self._encode_message(message) for message in request.messages],
            "stream": request.stream,
        }

        encoded_tools = [
            {"type": "function", "function": deepcopy(tool)}
            for tool in request.tools
        ]
        if encoded_tools:
            payload["tools"] = encoded_tools
        elif self.policy.empty_tools_policy == "empty_array":
            payload["tools"] = []

        if request.stream and self.policy.stream_usage_policy == "include":
            payload["stream_options"] = {"include_usage": True}
        if extra_body:
            payload["extra_body"] = extra_body
        payload.update(options)
        return payload
