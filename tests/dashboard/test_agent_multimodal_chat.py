"""Tests for dashboard multimodal chat message handling."""

from __future__ import annotations

import base64

from dojoagents.agent.multimodal import (
    normalize_openai_message_content,
    openai_content_has_images,
    openai_content_has_payload,
    openai_content_text,
    openai_content_to_strands_blocks,
)
from dojoagents.dashboard.server import _completion_request, _normalize_openai_messages


def test_normalize_openai_messages_preserves_image_parts():
    data_url = "data:image/png;base64," + base64.b64encode(b"abc").decode("ascii")
    messages = _normalize_openai_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe this"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]
    )
    assert len(messages) == 1
    content = messages[0]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"


def test_completion_request_accepts_image_only_user_message():
    data_url = "data:image/png;base64," + base64.b64encode(b"abc").decode("ascii")
    payload = {
        "model": "glm-4v",
        "messages": [
            {
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": data_url}}],
            }
        ],
        "metadata": {"session_id": "sess-img", "event_format": "dojo.v2"},
    }
    req, info = _completion_request(payload)
    assert req.message == ""
    assert req.metadata["user_content"][0]["type"] == "image_url"
    assert info["messages"][0]["content"][0]["type"] == "image_url"


def test_openai_content_to_strands_blocks_roundtrip_text_and_image():
    data_url = "data:image/jpeg;base64," + base64.b64encode(b"jpeg-bytes").decode("ascii")
    blocks = openai_content_to_strands_blocks(
        [
            {"type": "text", "text": "what is this"},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]
    )
    assert blocks[0]["text"] == "what is this"
    assert blocks[1]["image"]["format"] == "jpeg"
    assert blocks[1]["image"]["source"]["bytes"] == b"jpeg-bytes"


def test_openai_content_helpers():
    assert openai_content_text(" hello ") == "hello"
    assert openai_content_has_payload([{"type": "text", "text": "x"}]) is True
    assert openai_content_has_payload([{"type": "image_url", "image_url": {"url": "https://x.test/a.png"}}]) is True
    assert openai_content_has_images([{"type": "image_url", "image_url": {"url": "https://x.test/a.png"}}]) is True
    assert openai_content_has_images("plain text") is False
    normalized = normalize_openai_message_content([{"type": "text", "text": "only text"}])
    assert normalized == "only text"


def test_gemini_provider_preserves_image_parts():
    import base64

    from dojoagents.agent.gemini_provider import _messages_to_gemini_request

    data_url = "data:image/png;base64," + base64.b64encode(b"abc").decode("ascii")
    body = _messages_to_gemini_request(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        tools=[],
        model="gemini-2.5-flash",
        session_id="s1",
        provider_state=None,
        provider_name="gemini",
    )
    parts = body["contents"][0]["parts"]
    assert parts[0]["text"] == "describe"
    assert parts[1]["inline_data"]["mime_type"] == "image/png"
    assert parts[1]["inline_data"]["data"] == base64.b64encode(b"abc").decode("ascii")
