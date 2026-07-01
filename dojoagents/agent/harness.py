from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dojoagents.agent.models import ChatRequest, ToolCall, ToolResult


@dataclass
class HarnessDecision:
    complete: bool = True
    issues: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    allow_extra_steps: bool = False
    blocked_calls: list[dict[str, Any]] = field(default_factory=list)
    stop_code: str = "harness_incomplete"


@dataclass
class HarnessLoopState:
    request: ChatRequest
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    blocked_calls: list[dict[str, Any]] = field(default_factory=list)
    final_response: str = ""

    def last_tool_result(self, tool_name: str) -> ToolResult | None:
        for result in reversed(self.tool_results):
            if result.name == tool_name:
                return result
        return None

    def any_ok_tool(self, *tool_names: str) -> bool:
        names = set(tool_names)
        return any(result.ok and result.name in names for result in self.tool_results)

    def last_eval_submission(self):
        from dojoagents.agent.harnesses.portfolio_eval import parse_eval_submission

        for result in reversed(self.tool_results):
            if result.ok and result.name == "portfolio_eval_submit":
                parsed = parse_eval_submission(result.data)
                if parsed is not None:
                    return parsed
        return None

    def created_portfolio_ids(self) -> list[str]:
        ids: list[str] = []
        seen: set[str] = set()
        for result in self.tool_results:
            if not result.ok or result.name != "portfolio_write_create":
                continue
            portfolio_id: str | None = None
            data = result.data
            if isinstance(data, dict):
                raw_id = data.get("id") or data.get("portfolio_id")
                if raw_id:
                    portfolio_id = str(raw_id)
            if portfolio_id is None:
                for change in result.resource_changes:
                    if change.get("resource") == "portfolio" and change.get("action") == "create":
                        raw_id = change.get("portfolio_id")
                        if raw_id:
                            portfolio_id = str(raw_id)
                            break
            if portfolio_id and portfolio_id not in seen:
                seen.add(portfolio_id)
                ids.append(portfolio_id)
        return ids

    def created_portfolio_id(self) -> str | None:
        ids = self.created_portfolio_ids()
        return ids[-1] if ids else None

    def deleted_portfolio_ids(self) -> set[str]:
        deleted: set[str] = set()
        for result in self.tool_results:
            if not result.ok or result.name != "portfolio_write_delete":
                continue
            for change in result.resource_changes:
                if change.get("resource") == "portfolio" and change.get("portfolio_id"):
                    deleted.add(str(change["portfolio_id"]))
            data = result.data
            if isinstance(data, dict) and data.get("portfolio_id"):
                deleted.add(str(data["portfolio_id"]))
        return deleted

    def target_portfolio_id(self) -> str | None:
        created = self.created_portfolio_id()
        if created:
            return created
        deleted = self.deleted_portfolio_ids()
        for result in reversed(self.tool_results):
            if not result.ok or result.name not in {
                "portfolio_write_add_candidate",
                "portfolio_write_add_candidates",
                "portfolio_write_add_holding",
                "portfolio_write_add_holdings",
                "portfolio_write_create_order",
                "portfolio_write_create_orders",
                "portfolio_write_rename",
                "portfolio_write_auto_allocate",
                "portfolio_read_detail",
            }:
                continue
            for change in reversed(result.resource_changes):
                portfolio_id = change.get("portfolio_id")
                if change.get("resource") == "portfolio" and portfolio_id:
                    portfolio_id = str(portfolio_id)
                    if portfolio_id not in deleted:
                        return portfolio_id
            data = result.data
            if isinstance(data, dict):
                portfolio_id = data.get("portfolio_id") or data.get("id")
                if portfolio_id and str(portfolio_id) not in deleted:
                    return str(portfolio_id)
        return None

    def last_created_portfolio_id(self) -> str | None:
        return self.target_portfolio_id()


class TaskHarness:
    name = "task-harness"

    def matches(self, request: ChatRequest, state: HarnessLoopState) -> bool:
        return False

    def block_tool_call(self, call: ToolCall, state: HarnessLoopState) -> str | None:
        return None

    def repair_tool_calls(
        self,
        calls: list[ToolCall],
        state: HarnessLoopState,
    ) -> list[ToolCall]:
        return calls

    def validate_progress(self, state: HarnessLoopState) -> HarnessDecision:
        return HarnessDecision()

    def build_recovery_prompt(self, decision: HarnessDecision, locale: str) -> str:
        if locale == "zh":
            if decision.next_steps:
                return "任务还未完成：" + " ".join(decision.next_steps)
            if decision.issues:
                return "任务还未完成：" + "；".join(decision.issues)
            return "任务还未完成，请继续使用工具完成关键步骤。"
        if decision.next_steps:
            return "The task is not complete yet. " + " ".join(decision.next_steps)
        if decision.issues:
            return "The task is not complete yet. " + " ".join(decision.issues)
        return "The task is not complete yet. Continue using tools to finish the required work."

    def build_final_context(
        self,
        state: HarnessLoopState,
        locale: str,
    ) -> list[dict[str, Any]]:
        return []
