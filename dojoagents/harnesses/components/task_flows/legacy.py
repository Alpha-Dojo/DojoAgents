"""Temporary contracts for the pre-capability-graph task-flow adapter.

These types are domain-neutral and exist only while the synchronous legacy
Runtime facade is supported. New Harnesses should implement FlowPolicy specs
instead of registering ``TaskHarness`` instances.
"""

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
    escalation_code: str | None = None
    escalation_context: dict[str, Any] = field(default_factory=dict)


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


class TaskHarness:
    """Deprecated imperative task-flow interface."""

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


__all__ = ["HarnessDecision", "HarnessLoopState", "TaskHarness"]
