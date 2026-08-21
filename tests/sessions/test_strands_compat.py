import pytest

from dojoagents.config.models import SessionsConfig, StoreProviderConfig
from dojoagents.sessions.compat.strands import (
    canonical_to_strands,
    create_compat_session_manager,
    strands_to_canonical,
)
from dojoagents.sessions.models import SessionMessageRecord


def test_strands_canonical_conversion_preserves_supported_and_unknown_blocks():
    raw = {
        "role": "assistant",
        "content": [
            {"text": "analysis complete"},
            {
                "reasoningContent": {
                    "reasoningText": {
                        "text": "inspect the portfolio first",
                        "signature": "reasoning-signature",
                    },
                }
            },
            {"image": {"source": {"object_id": "image-1"}, "format": "png"}},
            {"document": {"source": {"object_id": "doc-1"}, "name": "report.pdf"}},
            {
                "toolUse": {
                    "toolUseId": "call-1",
                    "name": "quote",
                    "input": {"ticker": "AAPL"},
                    "dojoProviderMetadata": {"thought_signature": "sig-1"},
                }
            },
            {"toolResult": {"toolUseId": "call-1", "name": "quote", "status": "success", "content": [{"text": "123.4"}]}},
            {"redactedContent": {"data": "must-not-survive"}},
            {"providerFutureBlock": {"field": "value"}},
        ],
    }

    canonical = strands_to_canonical(
        raw,
        session_uid="uid-1",
        session_id="s1",
        agent_id="dojo-agent",
        sequence=1,
    )

    assert isinstance(canonical, SessionMessageRecord)
    assert [block["type"] for block in canonical.content] == [
        "reasoning",
        "text",
        "image_ref",
        "document_ref",
        "tool_use",
        "tool_result",
        "redacted",
        "provider_block",
    ]
    assert "must-not-survive" not in str(canonical.content)
    restored = canonical_to_strands(canonical)
    assert restored["role"] == "assistant"
    assert restored["content"][0] == raw["content"][1]
    assert restored["content"][1] == {"text": "analysis complete"}
    assert canonical.content[0] == {
        "type": "reasoning",
        "text": "inspect the portfolio first",
        "format": "reasoning_content",
        "status": "completed",
        "signature": "reasoning-signature",
    }
    assert canonical.raw_provider_payload == raw
    assert restored["content"][4]["toolUse"]["dojoProviderMetadata"] == {"thought_signature": "sig-1"}
    assert restored["content"][5]["toolResult"]["name"] == "quote"
    assert restored["content"][-1] == {"providerFutureBlock": {"field": "value"}}


def test_strands_compat_manager_is_file_only(tmp_path):
    file_config = SessionsConfig(
        store=StoreProviderConfig(
            provider="file",
            options={"root": str(tmp_path), "compatibility_mode": "dojo_repository"},
        )
    )
    manager = create_compat_session_manager(file_config, "s1")
    assert manager is not None

    sql_config = SessionsConfig(
        store=StoreProviderConfig(
            provider="mysql",
            factory="project.sessions:create_store",
            options={"dsn": "secret"},
        )
    )
    with pytest.raises(ValueError, match="file"):
        create_compat_session_manager(sql_config, "s1")


def test_reasoning_redacted_content_round_trips_as_json_safe_base64():
    raw = {
        "role": "assistant",
        "content": [{"reasoningContent": {"redactedContent": b"encrypted-reasoning"}}],
    }

    canonical = strands_to_canonical(
        raw,
        session_uid="uid-1",
        session_id="s1",
        agent_id="dojo-agent",
        sequence=1,
    )

    assert canonical.content == [
        {
            "type": "reasoning",
            "text": "",
            "format": "reasoning_content",
            "status": "completed",
            "encrypted_content": "ZW5jcnlwdGVkLXJlYXNvbmluZw==",
            "encrypted_encoding": "base64",
        }
    ]
    assert canonical.raw_provider_payload == {
        "role": "assistant",
        "content": [{"reasoningContent": {"redactedContent": {"base64": "ZW5jcnlwdGVkLXJlYXNvbmluZw=="}}}],
    }
    assert canonical_to_strands(canonical) == raw


def test_strands_file_mode_uses_configured_root(tmp_path):
    config = SessionsConfig(
        store=StoreProviderConfig(
            provider="file",
            options={"root": str(tmp_path), "compatibility_mode": "strands_file"},
        )
    )

    assert create_compat_session_manager(config, "s1") is not None
