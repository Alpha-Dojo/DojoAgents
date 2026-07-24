from __future__ import annotations

from pathlib import Path
from typing import Any

from dojoagents.agent.session_repository import DojoSessionRepository
from dojoagents.config.models import SessionsConfig
from dojoagents.sessions.models import JsonValue, SessionMessageRecord


def _canonical_block(block: dict[str, Any]) -> dict[str, JsonValue]:
    if "text" in block:
        return {"type": "text", "text": str(block.get("text") or "")}
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
        return {
            "type": "tool_use",
            "id": str(tool.get("toolUseId") or ""),
            "name": str(tool.get("name") or ""),
            "input": tool.get("input") if isinstance(tool.get("input"), dict) else {},
        }
    if "toolResult" in block:
        result = block.get("toolResult") if isinstance(block.get("toolResult"), dict) else {}
        content = result.get("content") if isinstance(result.get("content"), list) else []
        return {
            "type": "tool_result",
            "tool_use_id": str(result.get("toolUseId") or ""),
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
    content = raw.get("content")
    if isinstance(content, str):
        canonical: JsonValue = [{"type": "text", "text": content}]
    elif isinstance(content, list):
        canonical = [_canonical_block(block) for block in content if isinstance(block, dict)]
    else:
        canonical = []
    return SessionMessageRecord(
        session_uid=session_uid,
        session_id=session_id,
        agent_id=agent_id,
        sequence=sequence,
        role=str(raw.get("role") or "user"),
        content=canonical,
    )


def _strands_block(block: dict[str, Any]) -> dict[str, Any]:
    kind = block.get("type")
    if kind == "text":
        return {"text": str(block.get("text") or "")}
    if kind == "image_ref":
        return {"image": {key: block.get(key) for key in ("source", "format") if block.get(key) is not None}}
    if kind == "document_ref":
        return {"document": {key: block.get(key) for key in ("source", "name", "format") if block.get(key) is not None}}
    if kind == "tool_use":
        return {
            "toolUse": {
                "toolUseId": str(block.get("id") or ""),
                "name": str(block.get("name") or ""),
                "input": block.get("input") or {},
            }
        }
    if kind == "tool_result":
        result = {
            "toolUseId": str(block.get("tool_use_id") or ""),
            "content": [_strands_block(item) for item in (block.get("content") or []) if isinstance(item, dict)],
        }
        if block.get("status") is not None:
            result["status"] = block["status"]
        return {"toolResult": result}
    if kind == "redacted":
        return {"redactedContent": {"reason": str(block.get("reason") or "provider_redacted")}}
    if kind == "provider_block" and isinstance(block.get("raw"), dict):
        return dict(block["raw"])
    return {"text": ""}


def canonical_to_strands(record: SessionMessageRecord) -> dict[str, Any]:
    content = record.content
    blocks = content if isinstance(content, list) else [{"type": "text", "text": str(content or "")}]
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
