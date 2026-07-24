from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from dojoagents.agent.history_context import format_history_for_classifier
from dojoagents.logging import LOGGER

WRITE_SESSION_FILE_TOOL_NAME = "write_session_file"

_CLASSIFIER_SYSTEM_PROMPT = (
    "You decide whether an AI agent may write a session output file on behalf of the user.\n"
    "Respond ONLY with JSON (no markdown) using this schema:\n"
    "{\n"
    '  "allow_write": boolean,\n'
    '  "explanation": string\n'
    "}\n\n"
    "Rules:\n"
    "- allow_write=true ONLY when the user explicitly asked to save, export, write, download, "
    "or persist results to a file (JSON/JSONL/text/CSV/etc.), or clearly requested a file "
    "deliverable as part of the task.\n"
    "- allow_write=true when continuing unfinished work where the prior user task explicitly "
    "included saving/exporting a file (use session history).\n"
    "- allow_write=false when the agent would proactively save analysis output without the user "
    "requesting a file — deliverables should stay in the assistant reply instead.\n"
    "- allow_write=false for routine analysis, searches, updates, charts, or tables "
    "unless the user asked for a file."
)

_BLOCK_MESSAGE = (
    "Blocked {tool_name}: the user did not explicitly request a file export or save. "
    "{explanation} "
    "Deliver results in your assistant reply instead. "
    "Only call write_session_file when the user clearly asks to save, export, or download a file."
)

_GUARDRAIL_CODE = "write_session_file_user_request_required"


@dataclass(frozen=True)
class WriteSessionFileClassification:
    allow_write: bool = False
    explanation: str = ""


DEFAULT_WRITE_SESSION_FILE_CLASSIFICATION = WriteSessionFileClassification()


def active_task_metadata(request_metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(request_metadata, dict):
        return None
    active = request_metadata.get("active_task")
    if not isinstance(active, dict):
        return None
    task_id = str(active.get("task_id") or "").strip()
    return active if task_id else None


def task_required_output_filenames(request_metadata: dict[str, Any] | None) -> set[str]:
    active = active_task_metadata(request_metadata)
    if active is None:
        return set()
    outputs = active.get("outputs")
    if not isinstance(outputs, list):
        return set()
    names: set[str] = set()
    for item in outputs:
        if isinstance(item, dict):
            filename = str(item.get("filename") or "").strip()
            if filename:
                names.add(filename)
    return names


def should_allow_write_session_file_for_task(
    request_metadata: dict[str, Any] | None,
    *,
    filename: str = "",
) -> bool:
    """Task/pipeline runs declare required output artifacts; those writes are always allowed."""
    active = active_task_metadata(request_metadata)
    if active is None:
        return False
    required = task_required_output_filenames(request_metadata)
    if not required:
        return True
    safe_name = str(filename or "").strip()
    if not safe_name:
        return True
    return safe_name in required


def _parse_classifier_json(content: str) -> dict[str, Any] | None:
    text = (content or "").strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _coerce_write_session_file_classification(data: dict[str, Any]) -> WriteSessionFileClassification:
    allow_write = bool(data.get("allow_write", False))
    explanation = str(data.get("explanation") or "").strip()
    return WriteSessionFileClassification(allow_write=allow_write, explanation=explanation)


def _turn_cache_key(user_message: str, history: list | None) -> str:
    history_block = format_history_for_classifier(history or [], max_messages=4)
    payload = f"{(user_message or '').strip()}\n---\n{history_block}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def preview_write_content(content: Any, *, max_chars: int = 600) -> str:
    if content is None:
        return "(empty)"
    if isinstance(content, str):
        text = content.strip()
    else:
        try:
            text = json.dumps(content, ensure_ascii=False, default=str)
        except TypeError:
            text = str(content)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"


async def classify_write_session_file(
    user_message: str,
    llm_provider: Any,
    *,
    model: str,
    request_metadata: dict[str, Any] | None = None,
    filename: str = "",
    content_preview: str = "",
    history: list | None = None,
) -> WriteSessionFileClassification:
    """Use the configured LLM to decide whether a session file write is user-requested."""
    metadata = request_metadata if isinstance(request_metadata, dict) else {}
    if should_allow_write_session_file_for_task(metadata, filename=filename):
        return WriteSessionFileClassification(
            allow_write=True,
            explanation="Task mode required output artifact.",
        )
    cache_bucket = metadata.setdefault("_write_session_file_classifications", {})
    cache_key = _turn_cache_key(user_message, history)
    if isinstance(cache_bucket, dict) and cache_key in cache_bucket:
        cached = cache_bucket[cache_key]
        if isinstance(cached, dict):
            return _coerce_write_session_file_classification(cached)

    history_block = format_history_for_classifier(history or []) if history else "(no prior turns)"
    user_payload = (
        f"Latest user message:\n{(user_message or '').strip() or '(empty)'}\n\n"
        f"Recent session history:\n{history_block}\n\n"
        f"Proposed write_session_file call:\n"
        f"- filename: {(filename or '').strip() or '(unspecified)'}\n"
        f"- content preview:\n{(content_preview or '').strip() or '(empty)'}"
    )
    messages = [
        {"role": "system", "content": _CLASSIFIER_SYSTEM_PROMPT},
        {"role": "user", "content": user_payload},
    ]
    try:
        from dojoagents.agent.usage import usage_scope

        with usage_scope(
            "safety_classifier",
            "safety_classifier.write_session_file",
        ):
            result = await llm_provider.chat(messages, tools=[], model=model)
        data = _parse_classifier_json(result.content)
        if data is None:
            LOGGER.warning("write_session_file classifier returned non-JSON content; denying write")
            classification = WriteSessionFileClassification(
                allow_write=False,
                explanation="Could not classify user intent for file writes.",
            )
        else:
            classification = _coerce_write_session_file_classification(data)
        if isinstance(cache_bucket, dict):
            cache_bucket[cache_key] = {
                "allow_write": classification.allow_write,
                "explanation": classification.explanation,
            }
        return classification
    except Exception:
        LOGGER.exception("write_session_file classification failed; denying write")
        return WriteSessionFileClassification(
            allow_write=False,
            explanation="File-write intent classification failed.",
        )


def write_session_file_guardrail_from_classification(
    tool_name: str,
    classification: WriteSessionFileClassification,
) -> tuple[bool, str, str]:
    """Return (blocked, message, guardrail_code)."""
    if classification.allow_write:
        return False, "", "allow"
    explanation = classification.explanation or "No explicit user request to save a file was detected."
    message = _BLOCK_MESSAGE.format(tool_name=tool_name, explanation=explanation)
    return True, message, _GUARDRAIL_CODE
