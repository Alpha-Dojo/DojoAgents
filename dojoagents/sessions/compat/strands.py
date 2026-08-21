from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from dojoagents.agent.session_repository import DojoSessionRepository
from dojoagents.config.models import SessionsConfig
from dojoagents.sessions.models import JsonValue, SessionMessageRecord


def _json_safe(value: Any) -> JsonValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return {"base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)


def _canonical_block(block: dict[str, Any]) -> dict[str, JsonValue]:
    if "text" in block:
        return {"type": "text", "text": str(block.get("text") or "")}
    if "reasoningContent" in block:
        reasoning = block.get("reasoningContent") if isinstance(block.get("reasoningContent"), dict) else {}
        reasoning_text = reasoning.get("reasoningText") if isinstance(reasoning.get("reasoningText"), dict) else {}
        canonical_reasoning: dict[str, JsonValue] = {
            "type": "reasoning",
            "text": str(reasoning_text.get("text") or ""),
            "format": "reasoning_content",
            "status": "completed",
        }
        if reasoning_text.get("signature") is not None:
            canonical_reasoning["signature"] = str(reasoning_text["signature"])
        redacted = reasoning.get("redactedContent")
        if isinstance(redacted, bytes):
            canonical_reasoning["encrypted_content"] = base64.b64encode(redacted).decode("ascii")
            canonical_reasoning["encrypted_encoding"] = "base64"
        elif redacted is not None:
            canonical_reasoning["encrypted_content"] = redacted
        return canonical_reasoning
    if "image" in block:
        image = block.get("image") if isinstance(block.get("image"), dict) else {}
        return {
            "type": "image_ref",
            "source": image.get("source"),
            "format": image.get("format"),
        }
    if "document" in block:
        document = block.get("document") if isinstance(block.get("document"), dict) else {}
        return {
            "type": "document_ref",
            "source": document.get("source"),
            "name": document.get("name"),
            "format": document.get("format"),
        }
    if "toolUse" in block:
        tool = block.get("toolUse") if isinstance(block.get("toolUse"), dict) else {}
        canonical_tool: dict[str, JsonValue] = {
            "type": "tool_use",
            "id": str(tool.get("toolUseId") or ""),
            "name": str(tool.get("name") or ""),
            "input": tool.get("input") if isinstance(tool.get("input"), dict) else {},
        }
        provider_metadata = tool.get("dojoProviderMetadata")
        if isinstance(provider_metadata, dict) and provider_metadata:
            canonical_tool["provider_metadata"] = provider_metadata
        return canonical_tool
    if "toolResult" in block:
        result = block.get("toolResult") if isinstance(block.get("toolResult"), dict) else {}
        content = result.get("content") if isinstance(result.get("content"), list) else []
        return {
            "type": "tool_result",
            "tool_use_id": str(result.get("toolUseId") or ""),
            "name": str(result.get("name") or ""),
            "status": result.get("status"),
            "content": [_canonical_block(item) for item in content if isinstance(item, dict)],
        }
    if "redactedContent" in block:
        return {"type": "redacted", "reason": "provider_redacted"}
    return {"type": "provider_block", "raw": block}


def strands_to_canonical(
    raw: dict[str, Any],
    *,
    session_uid: str,
    session_id: str,
    agent_id: str,
    sequence: int,
) -> SessionMessageRecord:
    role = str(raw.get("role") or "user")
    content = raw.get("content")
    if isinstance(content, str):
        canonical: JsonValue = [{"type": "text", "text": content}]
    elif isinstance(content, list):
        canonical = [_canonical_block(block) for block in content if isinstance(block, dict)]
        if role == "assistant":
            canonical.sort(key=lambda block: block.get("type") != "reasoning")
    else:
        canonical = []
    return SessionMessageRecord(
        session_uid=session_uid,
        session_id=session_id,
        agent_id=agent_id,
        sequence=sequence,
        role=role,
        content=canonical,
        raw_provider_payload=_json_safe(raw) if role == "assistant" else None,
        schema_version=2,
    )


def _strands_block(block: dict[str, Any]) -> dict[str, Any]:
    kind = block.get("type")
    if kind == "text":
        return {"text": str(block.get("text") or "")}
    if kind == "reasoning":
        encrypted = block.get("encrypted_content")
        if encrypted is not None:
            if block.get("encrypted_encoding") == "base64" and isinstance(encrypted, str):
                encrypted = base64.b64decode(encrypted)
            return {"reasoningContent": {"redactedContent": encrypted}}
        reasoning_text = {"text": str(block.get("text") or "")}
        if block.get("signature") is not None:
            reasoning_text["signature"] = str(block["signature"])
        return {"reasoningContent": {"reasoningText": reasoning_text}}
    if kind == "image_ref":
        return {"image": {key: block.get(key) for key in ("source", "format") if block.get(key) is not None}}
    if kind == "document_ref":
        return {"document": {key: block.get(key) for key in ("source", "name", "format") if block.get(key) is not None}}
    if kind == "tool_use":
        tool_use = {
            "toolUseId": str(block.get("id") or ""),
            "name": str(block.get("name") or ""),
            "input": block.get("input") or {},
        }
        provider_metadata = block.get("provider_metadata")
        if isinstance(provider_metadata, dict) and provider_metadata:
            tool_use["dojoProviderMetadata"] = dict(provider_metadata)
        return {"toolUse": tool_use}
    if kind == "tool_result":
        result = {
            "toolUseId": str(block.get("tool_use_id") or ""),
            "content": [_strands_block(item) for item in (block.get("content") or []) if isinstance(item, dict)],
        }
        if block.get("status") is not None:
            result["status"] = block["status"]
        if block.get("name"):
            result["name"] = str(block["name"])
        return {"toolResult": result}
    if kind == "redacted":
        return {"redactedContent": {"reason": str(block.get("reason") or "provider_redacted")}}
    if kind == "provider_block" and isinstance(block.get("raw"), dict):
        return dict(block["raw"])
    return {"text": ""}


def canonical_to_strands(record: SessionMessageRecord) -> dict[str, Any]:
    content = record.content
    if isinstance(content, list):
        blocks = content
    elif isinstance(content, dict) and "type" in content:
        blocks = [content]
    elif isinstance(content, dict) and "text" in content:
        blocks = [{"type": "text", "text": str(content.get("text") or "")}]
    else:
        blocks = [{"type": "text", "text": str(content or "")}]
    return {
        "role": record.role,
        "content": [_strands_block(block) for block in blocks if isinstance(block, dict)],
    }


def create_compat_session_manager(config: SessionsConfig, session_id: str):
    if config.store.provider != "file":
        raise ValueError("Strands compatibility session manager is available only for the file store")
    options = config.store.options
    root = Path(str(options.get("root") or config.root)).expanduser().resolve()
    mode = str(options.get("compatibility_mode") or config.provider or "dojo_repository")
    if mode == "strands_file":
        from strands.session import FileSessionManager

        return FileSessionManager(session_id=session_id, storage_dir=str(root))
    if mode != "dojo_repository":
        raise ValueError(f"unsupported file compatibility mode: {mode}")
    from strands.session import RepositorySessionManager

    return RepositorySessionManager(
        session_id=session_id,
        session_repository=DojoSessionRepository(root),
    )
