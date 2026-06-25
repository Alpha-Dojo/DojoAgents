from __future__ import annotations

from dojoagents.agent.harness import HarnessDecision, HarnessLoopState, TaskHarness
from dojoagents.agent.models import ChatRequest, ToolCall

_PORTFOLIO_WRITE_TOOLS = {
    "portfolio_write_create",
    "portfolio_write_rename",
    "portfolio_write_delete",
    "portfolio_write_add_holding",
    "portfolio_write_remove_holding",
    "portfolio_write_auto_allocate",
}

_PORTFOLIO_ID_TOOLS = _PORTFOLIO_WRITE_TOOLS | {"portfolio_read_detail"}


class PortfolioTaskHarness(TaskHarness):
    name = "portfolio"

    def matches(self, request: ChatRequest, state: HarnessLoopState) -> bool:
        if request.channel != "dashboard":
            return False
        text = request.message.lower()
        return "portfolio" in text or "组合" in request.message or any(result.name.startswith("portfolio_") for result in state.tool_results)

    def repair_tool_calls(
        self,
        calls: list[ToolCall],
        state: HarnessLoopState,
    ) -> list[ToolCall]:
        portfolio_id = state.last_created_portfolio_id()
        repaired: list[ToolCall] = []
        for call in calls:
            if call.name in _PORTFOLIO_ID_TOOLS and not call.arguments.get("portfolio_id") and portfolio_id:
                next_args = dict(call.arguments)
                next_args["portfolio_id"] = portfolio_id
                repaired.append(ToolCall(id=call.id, name=call.name, arguments=next_args))
                continue
            repaired.append(call)
        return repaired

    def validate_progress(self, state: HarnessLoopState) -> HarnessDecision:
        wrote_portfolio = any(result.ok and result.name in _PORTFOLIO_WRITE_TOOLS for result in state.tool_results)
        verified = any(result.ok and result.name == "portfolio_read_detail" for result in state.tool_results)

        if wrote_portfolio and not verified:
            return HarnessDecision(
                complete=False,
                issues=["Portfolio changes require a verification read before the final answer."],
                next_steps=[
                    "Use portfolio_read_detail with the current portfolio_id to verify the saved portfolio before answering.",
                ],
                allow_extra_steps=True,
            )

        return HarnessDecision(complete=True)

    def build_recovery_prompt(self, decision: HarnessDecision, locale: str) -> str:
        portfolio_hint = "portfolio_read_detail"
        if locale == "zh":
            return "任务还未完成。请先调用 " f"{portfolio_hint} 校验刚才写入的组合结果，再给最终答复。"
        return "The task is not complete yet. " f"Call {portfolio_hint} to verify the saved portfolio state before giving the final answer."
