import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from dojoagents.agent.moonshot_provider import MoonshotProvider


@pytest.fixture
def mock_openai_client():
    with patch("openai.AsyncOpenAI") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.chat = MagicMock()
        mock_instance.chat.completions = MagicMock()
        mock_instance.chat.completions.create = AsyncMock()
        yield mock_instance.chat.completions.create


@pytest.mark.asyncio
async def test_moonshot_provider_thinking_temperature(mock_openai_client):
    mock_openai_client.return_value.choices = [MagicMock(message=MagicMock(content="response", tool_calls=None))]

    provider = MoonshotProvider(api_key="test-key", thinking=True)

    await provider.chat(
        messages=[{"role": "user", "content": "hello"}],
        tools=[],
        model="kimi-k2.5",
    )

    # Assert temperature is 1.0 when thinking is True
    mock_openai_client.assert_called_once()
    kwargs = mock_openai_client.call_args.kwargs
    assert kwargs.get("temperature") == 1.0
    assert kwargs.get("extra_body") == {"thinking": {"type": "enabled"}}


@pytest.mark.asyncio
async def test_moonshot_provider_no_thinking_temperature(mock_openai_client):
    mock_openai_client.return_value.choices = [MagicMock(message=MagicMock(content="response", tool_calls=None))]

    provider = MoonshotProvider(api_key="test-key", thinking=False)

    await provider.chat(
        messages=[{"role": "user", "content": "hello"}],
        tools=[],
        model="kimi-k2.5",
    )

    # Assert temperature is 0.6 when thinking is False
    mock_openai_client.assert_called_once()
    kwargs = mock_openai_client.call_args.kwargs
    assert kwargs.get("temperature") == 0.6
    assert kwargs.get("extra_body") == {"thinking": {"type": "disabled"}}


@pytest.mark.asyncio
async def test_moonshot_provider_preserves_reasoning_content(mock_openai_client):
    mock_openai_client.return_value.choices = [MagicMock(message=MagicMock(content="response", tool_calls=None))]

    provider = MoonshotProvider(api_key="test-key", thinking=True)

    messages = [
        {"role": "user", "content": "what is 2+2"},
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "I need to calculate 2+2, which is 4.",
            "tool_calls": [{"id": "1", "type": "function", "function": {"name": "calc", "arguments": "{}"}}],
        },
        {"role": "tool", "content": "4", "tool_call_id": "1"},
    ]

    await provider.chat(
        messages=messages,
        tools=[],
        model="kimi-k2.5",
    )

    mock_openai_client.assert_called_once()
    kwargs = mock_openai_client.call_args.kwargs
    sent_messages = kwargs.get("messages")

    # Assert the reasoning_content is preserved in the assistant message sent to the API
    assert len(sent_messages) == 3
    assert sent_messages[1]["role"] == "assistant"
    assert sent_messages[1]["reasoning_content"] == "I need to calculate 2+2, which is 4."
