"""Financial state kept outside the domain-neutral Harness loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from dojoagents.agent.harness import HarnessLoopState
from dojoagents.agent.harnesses.portfolio_task_intent import (
    classify_portfolio_task,
    is_liquidation_intent,
    order_side_trace,
)
from dojoagents.harnesses.state import HarnessSessionState
from dojoagents.sessions.errors import HarnessSessionIncompatibleError


def _legacy_state(context: Any) -> HarnessLoopState:
    return HarnessLoopState(
        request=context.request,
        tool_calls=list(context.tool_calls),
        tool_results=list(context.tool_results),
        tool_trace=[item for item in context.trace if isinstance(item, dict)],
        blocked_calls=[item for item in context.blocked_calls if isinstance(item, dict)],
        final_response=str(context.final_response or ""),
    )


@dataclass
class FinancialTurnState:
    created_portfolio_ids: list[str] = field(default_factory=list)
    deleted_portfolio_ids: set[str] = field(default_factory=set)
    target_portfolio_id: str | None = None
    last_eval_submission: dict[str, Any] | None = None
    candidate_count: int = 0
    position_count: int = 0
    has_buy_orders: bool = False
    has_sell_orders: bool = False
    liquidation_intent: bool = False
    task_kind: str = "none"
    sector_context: dict[str, Any] = field(default_factory=dict)
    tool_budget_used: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_context(cls, context: Any) -> "FinancialTurnState":
        state = cls()
        state.refresh(context)
        return state

    def refresh(self, context: Any) -> "FinancialTurnState":
        legacy = _legacy_state(context)
        self.created_portfolio_ids = legacy.created_portfolio_ids()
        self.deleted_portfolio_ids = legacy.deleted_portfolio_ids()
        self.target_portfolio_id = legacy.target_portfolio_id()
        self.liquidation_intent = is_liquidation_intent(context.request.message)
        self.task_kind = classify_portfolio_task(legacy)
        self.has_buy_orders, self.has_sell_orders = order_side_trace(legacy)

        eval_result = legacy.last_tool_result("portfolio_eval_submit")
        self.last_eval_submission = dict(eval_result.data) if eval_result and isinstance(eval_result.data, dict) else None
        detail = legacy.last_tool_result("portfolio_read_detail")
        detail_data = detail.data if detail and detail.ok and isinstance(detail.data, dict) else {}
        candidates = detail_data.get("candidates")
        self.candidate_count = len(candidates) if isinstance(candidates, list) else 0
        positions = detail_data.get("positions", detail_data.get("holdings"))
        self.position_count = sum(1 for row in positions if isinstance(row, dict) and float(row.get("shares") or 0) > 0) if isinstance(positions, list) else 0
        for result in reversed(context.tool_results):
            if result.ok and result.name == "search_sector_taxonomy" and isinstance(result.data, dict):
                best = result.data.get("best_match")
                if isinstance(best, dict):
                    self.sector_context = dict(best)
                    break
        counts: dict[str, int] = {}
        for item in context.trace:
            if isinstance(item, dict):
                name = str(item.get("tool_name") or item.get("tool") or item.get("name") or "")
            else:
                name = str(getattr(item, "tool_name", ""))
            if name:
                counts[name] = counts.get(name, 0) + 1
        self.tool_budget_used = counts
        return self


def financial_turn_state(context: Any, *, refresh: bool = True) -> FinancialTurnState:
    state = context.turn_state.values.get("financial")
    if not isinstance(state, FinancialTurnState):
        state = FinancialTurnState.from_context(context)
        context.turn_state.values["financial"] = state
    elif refresh:
        state.refresh(context)
    return state


class FinancialSessionStateCodec:
    """Whitelists cross-turn financial recovery state; turn counters never persist."""

    _keys = frozenset({"target_portfolio_id", "sector_context", "recovery"})

    @classmethod
    def _normalize(cls, data: Any) -> dict[str, Any]:
        raw = data if isinstance(data, Mapping) else {}
        financial = raw.get("financial", raw)
        if not isinstance(financial, Mapping):
            financial = {}
        return {
            "financial": {key: dict(value) if isinstance(value, Mapping) else value for key, value in financial.items() if key in cls._keys and value not in (None, "", {}, [])}
        }

    def encode(self, state: HarnessSessionState | Mapping[str, Any]) -> Mapping[str, Any]:
        values = state.values if isinstance(state, HarnessSessionState) else state
        return self._normalize(values)

    def decode(self, data: Mapping[str, Any]) -> HarnessSessionState:
        return HarnessSessionState(dict(self._normalize(data)))

    def migrate(
        self,
        state: Mapping[str, Any],
        *,
        from_version: str,
        from_schema_version: int,
        to_version: str,
        to_schema_version: int,
    ) -> Mapping[str, Any]:
        if from_schema_version > to_schema_version:
            raise HarnessSessionIncompatibleError("financial session state uses a newer schema and cannot be downgraded")
        if to_schema_version != 1 or from_schema_version < 0:
            raise HarnessSessionIncompatibleError("unsupported financial session state schema")
        raw = dict(state) if isinstance(state, Mapping) else {}
        if from_schema_version == 0 and "financial" not in raw:
            raw = {
                "financial": {
                    "target_portfolio_id": raw.get("target_portfolio_id") or raw.get("portfolio_id"),
                    "sector_context": raw.get("sector_context"),
                    "recovery": raw.get("recovery"),
                }
            }
        return self._normalize(raw)


__all__ = ["FinancialSessionStateCodec", "FinancialTurnState", "financial_turn_state"]
