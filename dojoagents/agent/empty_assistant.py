from __future__ import annotations

from typing import Any

from strands.types.session import SessionMessage

DOJO_INCOMPLETE_MARKER = "dojo_incomplete"
DOJO_INCOMPLETE_REASON = "dojo_incomplete_reason"
REASON_EMPTY_ASSISTANT = "empty_assistant_turn"

INCOMPLETE_PLACEHOLDER_ZH = (
    "[未完成：上轮助手未生成正文或工具调用。请从先前用户任务的中断处继续，"
    "必须给出面向用户的说明或继续调用工具完成交付。]"
)
INCOMPLETE_PLACEHOLDER_EN = (
    "[INCOMPLETE: prior assistant turn produced no text or tool calls. "
    "Resume the user's earlier task from where it stopped; provide user-facing "
    "text or continue with tools until the deliverable is ready.]"
)


def incomplete_placeholder(locale: str) -> str:
    return INCOMPLETE_PLACEHOLDER_ZH if locale == "zh" else INCOMPLETE_PLACEHOLDER_EN


def assistant_content_blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    if isinstance(content, str) and content.strip():
        return [{"text": content.strip()}]
    return []


def is_empty_assistant_content(content: Any) -> bool:
    blocks = assistant_content_blocks(content)
    if not blocks:
        return True
    has_text = any(str(block.get("text") or "").strip() for block in blocks if "text" in block)
    has_tool_use = any("toolUse" in block for block in blocks)
    return not has_text and not has_tool_use


def is_incomplete_assistant_message(raw: dict[str, Any]) -> bool:
    if str(raw.get("role") or "") != "assistant":
        return False
    metadata = raw.get("metadata")
    if isinstance(metadata, dict) and metadata.get(DOJO_INCOMPLETE_MARKER):
        return True
    blocks = assistant_content_blocks(raw.get("content"))
    for block in blocks:
        text = str(block.get("text") or "")
        if text.startswith("[未完成：") or text.startswith("[INCOMPLETE:"):
            return True
    return False


def mark_incomplete_assistant_payload(raw: dict[str, Any], *, locale: str = "en") -> dict[str, Any]:
    marked = dict(raw)
    metadata = dict(marked.get("metadata") or {})
    metadata[DOJO_INCOMPLETE_MARKER] = True
    metadata[DOJO_INCOMPLETE_REASON] = REASON_EMPTY_ASSISTANT
    marked["metadata"] = metadata
    marked["content"] = [{"text": incomplete_placeholder(locale)}]
    return marked


def sanitize_session_message(session_message: SessionMessage, *, locale: str = "en") -> SessionMessage:
    raw = session_message.to_message()
    if str(raw.get("role") or "") != "assistant":
        return session_message
    if not is_empty_assistant_content(raw.get("content")):
        return session_message
    if is_incomplete_assistant_message(raw):
        return session_message
    marked = mark_incomplete_assistant_payload(raw, locale=locale)
    return SessionMessage.from_message(marked, session_message.message_id)


def last_assistant_turn_empty(agent_messages: list[Any]) -> bool:
    for message in reversed(agent_messages or []):
        role = getattr(message, "role", None)
        if role is None and isinstance(message, dict):
            role = message.get("role")
        if str(role or "") != "assistant":
            continue
        content = getattr(message, "content", None)
        if content is None and isinstance(message, dict):
            content = message.get("content")
        return is_empty_assistant_content(content)
    return False


def build_empty_assistant_recovery_prompt(locale: str, *, tools_ran: bool) -> str:
    if locale == "zh":
        prefix = (
            "【空回复恢复】上一轮助手回合没有生成任何正文或工具调用，任务尚未完成。"
            "请继续完成先前用户请求：若还需数据请调用工具，若已有数据请给出面向用户的总结或交付物。"
            "禁止再次以空回复结束。"
        )
        if tools_ran:
            prefix += " 已有工具结果可供使用，请基于它们继续推进，不要重复相同工具调用。"
        return prefix
    prefix = (
        "[Empty reply recovery] The previous assistant turn produced no text or tool calls; "
        "the task is NOT complete. Continue the user's earlier request: call tools if more "
        "data is needed, otherwise provide user-facing summary or deliverables. "
        "Do NOT end with another empty reply."
    )
    if tools_ran:
        prefix += " Tool results from this run are already available — build on them instead of repeating identical calls."
    return prefix


def empty_assistant_user_message(locale: str) -> str:
    if locale == "zh":
        return (
            "助手在上一步没有生成有效回复（空输出）。请重新描述要继续的任务，"
            "或补充期望的交付物（例如图谱、分析结论、下一步工具操作）。"
        )
    return (
        "The assistant produced an empty reply on the previous step. "
        "Please restate the task to continue or specify the expected deliverable "
        "(for example a chart, analysis summary, or next tool action)."
    )
