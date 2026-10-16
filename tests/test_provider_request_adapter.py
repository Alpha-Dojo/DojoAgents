import pytest

from dojoagents.agent.provider_contracts import OpenAIRequestPolicy, ProviderRequest
from dojoagents.agent.provider_profiles import ModelIdPolicy
from dojoagents.agent.provider_request import OpenAIRequestAdapter


def _request(**overrides):
    values = {
        "model": "gpt-4.1",
        "messages": ({"role": "user", "content": "hello"},),
        "tools": (),
        "stream": False,
        "metadata": {},
        "options": {},
    }
    values.update(overrides)
    return ProviderRequest(**values)


def test_default_policy_omits_top_level_name_without_mutating_internal_message() -> None:
    internal = {
        "role": "assistant",
        "name": "research-agent",
        "content": "",
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "quote", "arguments": "{}"},
            }
        ],
    }

    payload = OpenAIRequestAdapter().build(_request(messages=(internal,)))

    assert "name" not in payload["messages"][0]
    assert payload["messages"][0]["tool_calls"][0]["function"]["name"] == "quote"
    assert internal["name"] == "research-agent"
    assert payload["messages"][0] is not internal
    assert payload["messages"][0]["tool_calls"] is not internal["tool_calls"]
    payload["messages"][0]["tool_calls"][0]["function"]["name"] = "changed"
    assert internal["tool_calls"][0]["function"]["name"] == "quote"


def test_preserve_policy_keeps_top_level_name() -> None:
    adapter = OpenAIRequestAdapter(OpenAIRequestPolicy(message_name_policy="preserve"))

    payload = adapter.build(
        _request(messages=({"role": "tool", "name": "quote", "content": "123.4"},))
    )

    assert payload["messages"][0]["name"] == "quote"


def test_tools_are_omitted_when_empty_and_encoded_in_input_order_when_present() -> None:
    adapter = OpenAIRequestAdapter()
    assert "tools" not in adapter.build(_request())

    first = {"name": "quote", "description": "Get a quote", "parameters": {}}
    second = {"name": "news", "description": "Get news", "parameters": {}}
    payload = adapter.build(_request(tools=(first, second)))

    assert [item["function"]["name"] for item in payload["tools"]] == ["quote", "news"]
    assert payload["tools"][0]["function"] is not first
    payload["tools"][0]["function"]["parameters"]["type"] = "object"
    assert first["parameters"] == {}


def test_empty_array_policy_emits_an_empty_tools_array() -> None:
    adapter = OpenAIRequestAdapter(OpenAIRequestPolicy(empty_tools_policy="empty_array"))

    assert adapter.build(_request())["tools"] == []


@pytest.mark.parametrize(
    ("stream", "policy", "expected"),
    [
        (True, OpenAIRequestPolicy(), {"include_usage": True}),
        (False, OpenAIRequestPolicy(), None),
        (True, OpenAIRequestPolicy(stream_usage_policy="unsupported"), None),
    ],
)
def test_stream_usage_policy(stream, policy, expected) -> None:
    payload = OpenAIRequestAdapter(policy).build(_request(stream=stream))

    assert payload.get("stream_options") == expected


@pytest.mark.parametrize(
    ("policy", "model", "expected"),
    [
        (ModelIdPolicy.AS_IS, "lab/model", "lab/model"),
        (ModelIdPolicy.AUTHOR_PREFIX, "model", "lab/model"),
        (ModelIdPolicy.AUTHOR_PREFIX, "lab/model", "lab/model"),
    ],
)
def test_model_id_policy(policy, model, expected) -> None:
    payload = OpenAIRequestAdapter(author="lab", model_id_policy=policy).build(
        _request(model=model)
    )

    assert payload["model"] == expected


def test_options_merge_extra_body_without_allowing_identity_overrides() -> None:
    request = _request(
        metadata={"_dojo_extra_body": {"enable_thinking": False, "source": "metadata"}},
        options={
            "temperature": 0.1,
            "max_completion_tokens": 4096,
            "extra_body": {"source": "option"},
        },
    )

    payload = OpenAIRequestAdapter().build(request)

    assert payload["temperature"] == 0.1
    assert payload["extra_body"] == {
        "enable_thinking": False,
        "source": "option",
    }
    assert payload["max_completion_tokens"] == 4096
    assert request.options["max_completion_tokens"] == 4096

    with pytest.raises(ValueError, match="cannot override"):
        OpenAIRequestAdapter().build(
            _request(options={"extra_body": {"messages": []}})
        )


def test_unsupported_options_and_non_mapping_extra_body_are_rejected() -> None:
    adapter = OpenAIRequestAdapter()

    with pytest.raises(ValueError, match="Unsupported"):
        adapter.build(_request(options={"unknown": True}))
    with pytest.raises(ValueError, match="must be a mapping"):
        adapter.build(_request(options={"extra_body": "invalid"}))
