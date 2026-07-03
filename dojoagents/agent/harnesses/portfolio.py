from __future__ import annotations

from typing import Any

from dojoagents.agent.escalation import STOP_CODE_NEEDS_USER_INPUT, find_user_input_escalation
from dojoagents.agent.harness import HarnessDecision, HarnessLoopState, TaskHarness
from dojoagents.agent.harnesses.portfolio_eval import (
    candidate_count_from_detail,
    parse_eval_submission,
    position_count_from_detail,
    verify_eval_submission,
)
from dojoagents.agent.harnesses.portfolio_task_intent import (
    classify_portfolio_task,
    order_side_trace,
)
from dojoagents.agent.models import ChatRequest, ToolCall

_PORTFOLIO_WRITE_TOOLS = {
    "portfolio_write_create",
    "portfolio_write_rename",
    "portfolio_write_delete",
    "portfolio_write_add_candidate",
    "portfolio_write_add_candidates",
    "portfolio_write_add_holding",
    "portfolio_write_add_holdings",
    "portfolio_write_create_order",
    "portfolio_write_create_orders",
    "portfolio_write_remove_holding",
    "portfolio_write_auto_allocate",
}

_PORTFOLIO_ID_TOOLS = _PORTFOLIO_WRITE_TOOLS | {"portfolio_read_detail", "portfolio_eval_submit"}

_ADD_CANDIDATE_TOOLS = {
    "portfolio_write_add_candidate",
    "portfolio_write_add_candidates",
    "portfolio_write_add_holding",
    "portfolio_write_add_holdings",
}

_CREATE_ORDER_TOOLS = {
    "portfolio_write_create_order",
    "portfolio_write_create_orders",
}

_ANALYSIS_BROWSE_TOOLS = {
    "portfolio_read_list",
    "portfolio_read_search",
    "portfolio_read_detail",
    "get_ticker_financials",
    "get_ticker_realtime_quote",
    "get_ticker_price_trends",
    "get_sector_analysis",
    "filter_sector_constituents",
    "search_sector_taxonomy",
    "screen_market_stocks",
    "search_company_ticker",
}

_MUTATING_BUILD_TOOLS = {
    "portfolio_write_create",
    *_ADD_CANDIDATE_TOOLS,
    *_CREATE_ORDER_TOOLS,
    "portfolio_write_remove_holding",
    "portfolio_write_auto_allocate",
}


class PortfolioTaskHarness(TaskHarness):
    name = "portfolio"

    def matches(self, request: ChatRequest, state: HarnessLoopState) -> bool:
        if request.channel != "dashboard":
            return False
        if find_user_input_escalation(state.tool_results):
            return True
        if state.any_ok_tool(*_PORTFOLIO_WRITE_TOOLS, "portfolio_eval_submit"):
            return True
        pending = {
            call.name
            for call in state.tool_calls
            if call.name in _PORTFOLIO_WRITE_TOOLS or call.name == "portfolio_eval_submit"
        }
        return bool(pending)

    def _portfolio_build_in_progress(self, state: HarnessLoopState) -> bool:
        return state.any_ok_tool("portfolio_write_create", *_ADD_CANDIDATE_TOOLS, *_CREATE_ORDER_TOOLS)

    def _run_is_analysis_browse(self, state: HarnessLoopState) -> bool:
        if state.any_ok_tool(*_PORTFOLIO_WRITE_TOOLS, "portfolio_eval_submit"):
            return False
        return state.any_ok_tool(*_ANALYSIS_BROWSE_TOOLS)

    def block_tool_call(self, call: ToolCall, state: HarnessLoopState) -> str | None:
        escalation = find_user_input_escalation(state.tool_results)
        if escalation is not None and call.name in _CREATE_ORDER_TOOLS:
            return (
                f"Blocked {call.name}: {escalation.message} "
                "Explain the issue to the user and wait for confirmation before retrying."
            )
        if call.name == "portfolio_write_create":
            if self._run_is_analysis_browse(state):
                return (
                    "Blocked portfolio_write_create: this run is analyzing/querying an existing portfolio. "
                    "Prior portfolio-creation tasks from earlier turns are closed. "
                    "Answer the current analysis request only."
                )
            active_id = state.target_portfolio_id()
            if state.any_ok_tool("portfolio_write_create") and active_id:
                return (
                    f"Blocked portfolio_write_create: this run already created portfolio {active_id}. "
                    "Reuse that portfolio_id — add candidates, portfolio_read_detail, "
                    "portfolio_eval_submit. Do NOT create another portfolio."
                )
        if call.name in _MUTATING_BUILD_TOOLS and call.name != "portfolio_write_delete":
            if self._run_is_analysis_browse(state):
                return (
                    f"Blocked {call.name}: this run is read/analysis only. "
                    "Do not modify portfolios unless the current user message explicitly asks to create, "
                    "add candidates, or open positions."
                )
        if call.name != "portfolio_write_delete":
            return None
        if not self._portfolio_build_in_progress(state):
            return None
        return (
            "Blocked portfolio_write_delete: this run is building a portfolio (create/add). "
            "Finish the task, call portfolio_read_detail, then portfolio_eval_submit. "
            "Do not delete portfolios while adding candidates."
        )

    def repair_tool_calls(
        self,
        calls: list[ToolCall],
        state: HarnessLoopState,
    ) -> list[ToolCall]:
        portfolio_id = state.target_portfolio_id()
        repaired: list[ToolCall] = []
        for call in calls:
            if call.name in _PORTFOLIO_ID_TOOLS and not call.arguments.get("portfolio_id") and portfolio_id:
                next_args = dict(call.arguments)
                next_args["portfolio_id"] = portfolio_id
                repaired.append(
                    ToolCall(id=call.id, name=call.name, arguments=next_args, metadata=dict(call.metadata))
                )
                continue
            repaired.append(call)
        return repaired

    def validate_progress(self, state: HarnessLoopState) -> HarnessDecision:
        escalation = self._user_input_escalation_decision(state)
        if escalation is not None:
            return escalation

        if self._is_delete_only_task(state):
            return self._validate_delete_progress(state)

        wrote_portfolio = any(result.ok and result.name in _PORTFOLIO_WRITE_TOOLS for result in state.tool_results)
        eval_submission = state.last_eval_submission()
        detail_result = state.last_tool_result("portfolio_read_detail")
        detail_data = detail_result.data if detail_result and detail_result.ok else None

        if not wrote_portfolio and eval_submission is None:
            return HarnessDecision(complete=True)

        if not isinstance(detail_data, dict):
            return HarnessDecision(
                complete=False,
                issues=["Portfolio writes require portfolio_read_detail verification before completion."],
                next_steps=[
                    "Call portfolio_read_detail for the target portfolio_id, "
                    "then portfolio_eval_submit with your success criteria.",
                ],
                allow_extra_steps=True,
            )

        if eval_submission is None:
            task_kind = classify_portfolio_task(state)
            return HarnessDecision(
                complete=False,
                issues=["Agent must submit eval criteria before claiming the portfolio task is done."],
                next_steps=self._eval_submit_next_steps(task_kind, state),
                allow_extra_steps=True,
            )

        eval_issues = verify_eval_submission(eval_submission, detail_data)
        if eval_issues:
            task_kind = classify_portfolio_task(state)
            return HarnessDecision(
                complete=False,
                issues=eval_issues,
                next_steps=self._eval_recovery_next_steps(eval_issues, task_kind, state),
                allow_extra_steps=True,
            )

        objective_issues = self._objective_create_issues(state, detail_data)
        if objective_issues:
            task_kind = classify_portfolio_task(state)
            return HarnessDecision(
                complete=False,
                issues=objective_issues,
                next_steps=self._objective_recovery_next_steps(objective_issues, task_kind, state, detail_data),
                allow_extra_steps=True,
            )

        # Eval verified — stop immediately; do not re-enter recovery for historical trace noise.
        return HarnessDecision(complete=True)

    def _is_delete_only_task(self, state: HarnessLoopState) -> bool:
        if not state.any_ok_tool("portfolio_write_delete"):
            return False
        if state.any_ok_tool(*_MUTATING_BUILD_TOOLS):
            return False
        for result in state.tool_results:
            if not result.ok or result.name not in _PORTFOLIO_WRITE_TOOLS:
                continue
            if result.name != "portfolio_write_delete":
                return False
        return True

    def _validate_delete_progress(self, state: HarnessLoopState) -> HarnessDecision:
        deleted_ids = state.deleted_portfolio_ids()
        if not deleted_ids:
            return HarnessDecision(
                complete=False,
                issues=["Delete task requires a successful portfolio_write_delete."],
                next_steps=["Call portfolio_write_delete for the target portfolio_id."],
                allow_extra_steps=True,
            )

        list_result = state.last_tool_result("portfolio_read_list")
        list_data = list_result.data if list_result and list_result.ok else None
        rows: list[Any] = []
        if isinstance(list_data, list):
            rows = list_data
        elif isinstance(list_data, dict):
            raw_rows = list_data.get("items") or list_data.get("portfolios")
            if isinstance(raw_rows, list):
                rows = raw_rows

        for row in rows:
            if not isinstance(row, dict):
                continue
            portfolio_id = str(row.get("id") or row.get("portfolio_id") or "")
            if portfolio_id in deleted_ids:
                return HarnessDecision(
                    complete=False,
                    issues=[f"Deleted portfolio {portfolio_id} still appears in portfolio_read_list."],
                    next_steps=["Retry portfolio_write_delete or refresh portfolio_read_list."],
                    allow_extra_steps=True,
                )

        return HarnessDecision(complete=True)

    def _trace_integrity_issues(self, state: HarnessLoopState) -> list[str]:
        issues: list[str] = []
        if state.any_ok_tool("portfolio_write_delete") and self._portfolio_build_in_progress(state):
            issues.append("portfolio_write_delete ran during the same build run as create/add.")
        created_id = state.created_portfolio_id()
        if created_id and created_id in state.deleted_portfolio_ids():
            issues.append("The portfolio created in this run was deleted before the task finished.")
        return issues

    def _objective_create_issues(self, state: HarnessLoopState, detail_data: dict[str, Any]) -> list[str]:
        """Facts from tool trace — not parsed from user text."""
        issues: list[str] = []
        task_kind = classify_portfolio_task(state)
        has_ok_buy, has_ok_sell = order_side_trace(state)
        position_count = position_count_from_detail(detail_data)

        create_ids = state.created_portfolio_ids()
        if len(create_ids) > 1:
            issues.append(
                f"This run created {len(create_ids)} portfolios ({', '.join(create_ids)}); "
                "only one portfolio_write_create is allowed per task."
            )
        if state.any_ok_tool("portfolio_write_create") and str(detail_data.get("kind") or "") != "agent":
            issues.append("portfolio_write_create was used but verified portfolio kind is not agent.")
        eval_submission = state.last_eval_submission()
        if (
            state.any_ok_tool("portfolio_write_create")
            and eval_submission is not None
            and not eval_submission.require_kind_agent
        ):
            issues.append("portfolio_eval_submit must set require_kind_agent=true when portfolio_write_create was used.")
        if state.any_ok_tool(*_ADD_CANDIDATE_TOOLS) and candidate_count_from_detail(detail_data) <= 0:
            issues.append("Candidates were added but portfolio_read_detail shows zero candidates.")
        if has_ok_buy and position_count <= 0:
            issues.append(
                "Buy orders were placed but portfolio_read_detail shows zero filled positions — "
                "check order fill errors (price, qty, capital)."
            )
        if task_kind == "liquidate" and has_ok_sell and position_count > 0:
            issues.append(
                f"Liquidation incomplete: portfolio_read_detail still shows {position_count} open position(s)."
            )
        if (
            eval_submission is not None
            and eval_submission.require_kind_agent
            and str(detail_data.get("kind") or "") != "agent"
            and not state.any_ok_tool("portfolio_write_create")
        ):
            issues.append(
                "require_kind_agent=true is only for agent-created portfolios; "
                "set require_kind_agent=false for manual portfolios."
            )
        return issues

    def _eval_submit_next_steps(self, task_kind: str, state: HarnessLoopState) -> list[str]:
        if task_kind == "liquidate":
            return [
                "Call portfolio_eval_submit after portfolio_read_detail confirms position_count=0. "
                "Use max_position_count=0 and require_kind_agent=false. "
                "Do NOT add candidates or portfolio_write_create.",
            ]
        if task_kind == "trade" and not state.any_ok_tool("portfolio_write_create"):
            return [
                "Call portfolio_eval_submit after portfolio_read_detail with task-appropriate criteria. "
                "For manual portfolios use require_kind_agent=false.",
            ]
        return [
            "Call portfolio_eval_submit after portfolio_read_detail. "
            "Use min_candidate_count for watchlist tasks, min_position_count for 建仓, "
            "and require_kind_agent=true only when portfolio_write_create was used in this run.",
        ]

    def _eval_recovery_next_steps(
        self,
        issues: list[str],
        task_kind: str,
        state: HarnessLoopState,
    ) -> list[str]:
        joined = " ".join(issues).lower()
        if "not agent-owned" in joined or "require_kind_agent=true is only" in joined:
            return [
                "Set require_kind_agent=false for manual portfolios.",
                "Call portfolio_read_detail, then portfolio_eval_submit with corrected criteria.",
            ]
        if task_kind == "liquidate" or "at most 0" in joined:
            return [
                "Complete remaining sell orders until position_count=0.",
                "portfolio_eval_submit with max_position_count=0 and require_kind_agent=false.",
            ]
        return [
            "Update the portfolio to satisfy your portfolio_eval_submit criteria, "
            "call portfolio_read_detail again, then portfolio_eval_submit with corrected expectations "
            "or fix the portfolio and re-verify.",
        ]

    def _objective_recovery_next_steps(
        self,
        issues: list[str],
        task_kind: str,
        state: HarnessLoopState,
        detail_data: dict[str, Any],
    ) -> list[str]:
        joined = " ".join(issues).lower()
        if "require_kind_agent=true is only for agent-created" in joined or "not agent-owned" in joined:
            return [
                "Set require_kind_agent=false for this manual portfolio.",
                "Call portfolio_read_detail, then portfolio_eval_submit with corrected criteria.",
            ]
        if "zero filled positions" in joined or "buy orders were placed" in joined:
            return [
                "Fix buy order fill errors (price, qty, capital).",
                "Call portfolio_read_detail, then portfolio_eval_submit with min_position_count matching filled positions.",
            ]
        if "liquidation incomplete" in joined:
            return [
                "Place remaining sell orders for open positions.",
                "Call portfolio_read_detail, then portfolio_eval_submit with max_position_count=0 and require_kind_agent=false.",
            ]
        if "zero candidates" in joined:
            return [
                "Add missing candidates with portfolio_write_add_candidates.",
                "Call portfolio_read_detail, then portfolio_eval_submit with min_candidate_count.",
            ]
        if "require_kind_agent=true when portfolio_write_create" in joined:
            return [
                "Call portfolio_eval_submit with require_kind_agent=true after portfolio_read_detail.",
            ]
        if task_kind == "liquidate":
            return [
                "Confirm liquidation via portfolio_read_detail (position_count=0).",
                "portfolio_eval_submit with max_position_count=0 and require_kind_agent=false. "
                "Do NOT add candidates or portfolio_write_create.",
            ]
        if task_kind == "trade":
            return [
                "Fix the existing portfolio from this run (do NOT portfolio_write_create again).",
                "Call portfolio_read_detail, then portfolio_eval_submit with require_kind_agent=false for manual portfolios.",
            ]
        return [
            "Fix the existing portfolio from this run (do NOT portfolio_write_create again).",
            "Call portfolio_read_detail, then portfolio_eval_submit with criteria matching the user task.",
        ]

    def _user_input_escalation_decision(self, state: HarnessLoopState) -> HarnessDecision | None:
        signal = find_user_input_escalation(state.tool_results)
        if signal is None:
            return None
        return HarnessDecision(
            complete=False,
            stop_code=STOP_CODE_NEEDS_USER_INPUT,
            allow_extra_steps=False,
            issues=[signal.message],
            next_steps=list(signal.context.get("user_options") or []),
            escalation_code=signal.code,
            escalation_context=dict(signal.context),
        )

    def build_recovery_prompt(self, decision: HarnessDecision, locale: str) -> str:
        if decision.stop_code == STOP_CODE_NEEDS_USER_INPUT:
            return self._build_user_input_prompt(decision, locale)
        return self._build_eval_recovery_prompt(decision, locale)

    def _build_user_input_prompt(self, decision: HarnessDecision, locale: str) -> str:
        options = decision.next_steps or list(decision.escalation_context.get("user_options") or [])
        options_text = " ".join(options)
        if locale == "zh":
            prefix = (
                "【需用户确认】当前任务遇到无法由 Agent 单方面解决的约束，已停止自动重试。"
                "禁止擅自降低仓位或修改股数。向用户说明预算缺口与可选方案，等待用户确认后再继续。"
            )
            if decision.issues:
                prefix += " 原因：" + "；".join(decision.issues)
            if options_text:
                return prefix + " 可选方案：" + options_text
            return prefix
        prefix = (
            "[Needs user input] The task hit a constraint the agent cannot fix alone. "
            "Auto-retry is stopped. Do NOT silently reduce share counts. "
            "Explain the gap and present options; wait for the user before placing more orders."
        )
        if decision.issues:
            prefix += " Reason: " + " ".join(decision.issues)
        if options_text:
            return prefix + " Options: " + options_text
        return prefix

    def _build_eval_recovery_prompt(self, decision: HarnessDecision, locale: str) -> str:
        if locale == "zh":
            prefix = (
                "【Eval 未通过】任务尚未完成，禁止向用户宣称已成功。"
                "不要重复输出完整组合报告/表格/投资亮点。"
                "不要调用 portfolio_write_create 新建组合；只修复当前组合。"
                "只说明缺口并调用工具修复（修正 eval 门槛、read_detail 后再 eval_submit）。"
            )
            if decision.issues:
                prefix += " 问题：" + "；".join(decision.issues)
            if decision.next_steps:
                return prefix + " 下一步：" + " ".join(decision.next_steps)
            return prefix + " 请 portfolio_read_detail + portfolio_eval_submit 完成自检。"
        prefix = (
            "[Eval failed] Task NOT complete. Do NOT tell the user it succeeded. "
            "Do NOT repeat the full portfolio report, tables, or marketing summary. "
            "Do NOT call portfolio_write_create again — fix the existing portfolio from this run. "
            "State only the gap and fix via tools (adjust eval thresholds, "
            "portfolio_read_detail then portfolio_eval_submit)."
        )
        if decision.issues:
            prefix += " Issues: " + " ".join(decision.issues)
        if decision.next_steps:
            return prefix + " Next: " + " ".join(decision.next_steps)
        return prefix + " Use portfolio_read_detail then portfolio_eval_submit before answering."
