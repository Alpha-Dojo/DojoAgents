from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from dojoagents.agent.models import ChatRequest
from dojoagents.agent.history_context import (
    format_history_for_classifier,
    history_message_text,
)
from dojoagents.logging import LOGGER

TurnIntentMode = Literal["continue_unfinished", "new_task"]
LastTurnStatus = Literal["tools_only_no_deliverable", "empty_reply", "complete", "unknown"]

_CLASSIFIER_SYSTEM_PROMPT = (
    "You classify the user's latest message in a multi-turn finance agent session.\n"
    "Respond ONLY with JSON (no markdown) using this schema:\n"
    "{\n"
    '  "continue_unfinished": boolean,\n'
    '  "prior_task_summary": string,\n'
    '  "last_turn_status": "tools_only_no_deliverable" | "empty_reply" | "complete" | "unknown"\n'
    "}\n\n"
    "Rules:\n"
    "- continue_unfinished=true when the user wants to resume or continue work from earlier "
    "in the session rather than starting a brand-new unrelated task.\n"
    "- continue_unfinished=false when the user asks a new independent question.\n"
    "- prior_task_summary: one concise sentence describing the unfinished task from session "
    "history (empty when continue_unfinished=false).\n"
    "- last_turn_status: classify the most recent assistant turn in history."
)


@dataclass(frozen=True)
class TurnIntentResult:
    mode: TurnIntentMode = "new_task"
    prior_task_summary: str = ""
    last_turn_status: LastTurnStatus = "unknown"


DEFAULT_TURN_INTENT = TurnIntentResult()


_history_message_text = history_message_text
_format_history_for_classifier = format_history_for_classifier


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


def _coerce_turn_intent(data: dict[str, Any]) -> TurnIntentResult:
    continue_unfinished = bool(data.get("continue_unfinished"))
    prior_task_summary = str(data.get("prior_task_summary") or "").strip()
    raw_status = str(data.get("last_turn_status") or "unknown").strip().lower()
    valid_statuses = {"tools_only_no_deliverable", "empty_reply", "complete", "unknown"}
    last_turn_status: LastTurnStatus = raw_status if raw_status in valid_statuses else "unknown"
    mode: TurnIntentMode = "continue_unfinished" if continue_unfinished else "new_task"
    return TurnIntentResult(
        mode=mode,
        prior_task_summary=prior_task_summary,
        last_turn_status=last_turn_status,
    )


def _cache_turn_intent(request: ChatRequest, intent: TurnIntentResult) -> None:
    request.metadata["_turn_intent_result"] = {
        "continue_unfinished": intent.mode == "continue_unfinished",
        "prior_task_summary": intent.prior_task_summary,
        "last_turn_status": intent.last_turn_status,
    }


async def classify_turn_intent(
    request: ChatRequest,
    llm_provider: Any,
    *,
    model: str,
) -> TurnIntentResult:
    """Use the configured LLM to classify turn scope (new task vs resume unfinished work)."""
    message = str(request.message or "").strip()
    if not message:
        return DEFAULT_TURN_INTENT

    cached = request.metadata.get("_turn_intent_result")
    if isinstance(cached, dict):
        return _coerce_turn_intent(cached)

    history = request.metadata.get("history") or []
    history_block = _format_history_for_classifier(history) if history else "(no prior turns)"
    user_payload = f"Latest user message:\n{message}\n\n" f"Recent session history:\n{history_block}"
    messages = [
        {"role": "system", "content": _CLASSIFIER_SYSTEM_PROMPT},
        {"role": "user", "content": user_payload},
    ]
    try:
        from dojoagents.agent.usage import usage_scope

        with usage_scope(
            "turn_intent",
            "turn_intent.financial",
        ):
            result = await llm_provider.chat(messages, tools=[], model=model)
        data = _parse_classifier_json(result.content)
        if data is None:
            LOGGER.warning("Turn intent classifier returned non-JSON content; using defaults")
            return DEFAULT_TURN_INTENT
        intent = _coerce_turn_intent(data)
        _cache_turn_intent(request, intent)
        return intent
    except Exception:
        LOGGER.exception("Turn intent classification failed; using defaults")
        return DEFAULT_TURN_INTENT


def format_unfinished_task_summary(intent: TurnIntentResult, locale: str) -> str:
    parts: list[str] = []
    if intent.prior_task_summary:
        clipped = intent.prior_task_summary
        if len(clipped) > 1200:
            clipped = clipped[:1200] + "…"
        if locale == "zh":
            parts.append(f"先前用户任务：{clipped}")
        else:
            parts.append(f"Prior user task: {clipped}")

    if intent.last_turn_status == "tools_only_no_deliverable":
        if locale == "zh":
            parts.append("上一轮助手仅有工具步骤占位，没有面向用户的交付正文。")
        else:
            parts.append("The last assistant turn only had a tools-complete placeholder, not a user deliverable.")
    elif intent.last_turn_status == "empty_reply":
        if locale == "zh":
            parts.append("上一轮助手回复为空。")
        else:
            parts.append("The last assistant reply was empty.")

    if not parts:
        if locale == "zh":
            return "用户在会话更早轮次提出的任务（请从 session 历史中恢复具体目标并继续执行）。"
        return "The user's task from earlier in this session (recover the concrete goal from session history and continue)."
    return "\n".join(parts)


def build_turn_intent_anchor(request: ChatRequest, intent: TurnIntentResult) -> str:
    """Scope the model to the latest user message when prior turns exist."""
    history = request.metadata.get("history") or []
    if not history:
        return ""

    message = str(request.message or "").strip()
    if not message:
        return ""

    locale = str(request.metadata.get("locale") or "en")
    if intent.mode == "continue_unfinished":
        summary = format_unfinished_task_summary(intent, locale)
        if locale == "zh":
            return (
                "## 当前任务（续做未完成工作）\n"
                f"用户最新消息：{message}\n\n"
                f"{summary}\n\n"
                "用户明确要求继续先前未完成的任务。请从上次中断处接着做，不要当作新任务重新开始，"
                "也不要在未完成时宣称已成功。必须给出面向用户的正文，或在需要时继续调用工具完成交付物。"
            )
        return (
            "## Active Task (RESUME unfinished work)\n"
            f"Latest user message: {message}\n\n"
            f"{summary}\n\n"
            "The user explicitly asked to continue unfinished work from earlier in this session. "
            "Resume from the last checkpoint — do NOT restart as a brand-new task or claim success early. "
            "Provide user-facing text and/or continue with tools until the deliverable is ready."
        )

    if locale == "zh":
        return (
            "## 当前任务（仅本条消息）\n"
            f"用户最新消息：{message}\n\n"
            "会话中更早的轮次视为已结束。不要继续执行旧任务（例如上一轮的选股、创建组合、建仓），"
            "除非本条消息明确要求。只完成当前问题；若当前是分析/解读，禁止调用 portfolio_write_create "
            "或批量添加候选股。"
        )
    return (
        "## Active Task (THIS user message only)\n"
        f"Latest user message: {message}\n\n"
        "Earlier turns are closed — do NOT resume prior tasks (e.g. stock picking, portfolio creation, "
        "position building) unless THIS message explicitly asks. Fulfill only the current request. "
        "For analysis/read-only questions, do NOT call portfolio_write_create or batch add candidates."
    )


async def build_turn_intent_anchor_async(
    request: ChatRequest,
    llm_provider: Any,
    *,
    model: str,
) -> tuple[str, TurnIntentResult]:
    intent = await classify_turn_intent(request, llm_provider, model=model)
    return build_turn_intent_anchor(request, intent), intent
