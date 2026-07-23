"""Domain-neutral formatting helpers for bounded classifier history."""

from __future__ import annotations

from typing import Any


def history_message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            elif isinstance(block, dict) and "text" in block:
                parts.append(str(block.get("text") or ""))
        return "".join(parts).strip()
    return str(content or "").strip()


def format_history_for_classifier(history: list[Any], *, max_messages: int = 8) -> str:
    lines: list[str] = []
    for message in history[-max_messages:]:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "?")
        text = history_message_text(message)
        if not text and role == "assistant":
            metadata = message.get("metadata")
            text = "[incomplete assistant turn]" if isinstance(metadata, dict) and metadata.get("dojo_incomplete") else "[empty assistant content]"
        if not text:
            continue
        clipped = text if len(text) <= 800 else text[:800] + "…"
        lines.append(f"{role}: {clipped}")
    return "\n".join(lines)


__all__ = ["format_history_for_classifier", "history_message_text"]
