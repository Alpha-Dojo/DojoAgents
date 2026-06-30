from __future__ import annotations

from dojoagents.agent.models import ChatRequest


def build_turn_intent_anchor(request: ChatRequest) -> str:
    """Scope the model to the latest user message when prior turns exist."""
    history = request.metadata.get("history") or []
    if not history:
        return ""

    message = str(request.message or "").strip()
    if not message:
        return ""

    locale = str(request.metadata.get("locale") or "en")
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
