"""Repair portfolio tool calls before execution (batch merge, etc.)."""

from __future__ import annotations

from dojoagents.agent.models import ToolCall
from dojoagents.logging import get_logger

LOGGER = get_logger(__name__)

_REMOVE_HOLDING_TOOL = "portfolio_write_remove_holding"
_REMOVE_CANDIDATES_TOOL = "portfolio_write_remove_candidates"


def merge_remove_holding_tool_calls(tool_calls: list[ToolCall]) -> list[ToolCall]:
    """Merge 2+ portfolio_write_remove_holding calls for the same portfolio into one batch."""
    if len(tool_calls) < 2:
        return tool_calls

    groups: dict[str, list[ToolCall]] = {}
    for call in tool_calls:
        if call.name != _REMOVE_HOLDING_TOOL:
            continue
        portfolio_id = str(call.arguments.get("portfolio_id") or "").strip()
        if not portfolio_id:
            continue
        groups.setdefault(portfolio_id, []).append(call)

    mergeable = {portfolio_id: calls for portfolio_id, calls in groups.items() if len(calls) >= 2}
    if not mergeable:
        return tool_calls

    merged_by_portfolio: dict[str, ToolCall] = {}
    for portfolio_id, calls in mergeable.items():
        holdings: list[dict[str, str]] = []
        seen: set[tuple[str, str | None]] = set()
        for call in calls:
            ticker = str(call.arguments.get("ticker") or "").strip()
            if not ticker:
                continue
            market_raw = call.arguments.get("market")
            market = str(market_raw).strip().lower() if market_raw is not None else None
            if market == "":
                market = None
            key = (ticker.upper(), market)
            if key in seen:
                continue
            seen.add(key)
            entry: dict[str, str] = {"ticker": ticker}
            if market is not None:
                entry["market"] = market
            holdings.append(entry)

        if len(holdings) < 2:
            continue

        first = calls[0]
        merged_by_portfolio[portfolio_id] = ToolCall(
            id=first.id,
            name=_REMOVE_CANDIDATES_TOOL,
            arguments={"portfolio_id": portfolio_id, "holdings": holdings},
            metadata=dict(first.metadata),
        )
        LOGGER.info(
            "Merged %d portfolio_write_remove_holding calls into portfolio_write_remove_candidates "
            "for portfolio_id=%s",
            len(calls),
            portfolio_id,
        )

    if not merged_by_portfolio:
        return tool_calls

    absorbed_ids = {
        call.id
        for portfolio_id, calls in mergeable.items()
        if portfolio_id in merged_by_portfolio
        for call in calls
    }

    repaired: list[ToolCall] = []
    inserted: set[str] = set()
    for call in tool_calls:
        if call.name == _REMOVE_HOLDING_TOOL:
            portfolio_id = str(call.arguments.get("portfolio_id") or "").strip()
            if portfolio_id in merged_by_portfolio:
                if portfolio_id not in inserted:
                    repaired.append(merged_by_portfolio[portfolio_id])
                    inserted.add(portfolio_id)
                continue
        if call.id in absorbed_ids:
            continue
        repaired.append(call)
    return repaired
