from __future__ import annotations

import re
from typing import Any, Literal

from ..legacy_harness import HarnessLoopState

PortfolioTaskKind = Literal["build", "liquidate", "trade", "delete", "none"]

_SYNC_POSITION_TOOL_NAMES = frozenset(
    {
        "portfolio_write_sync_positions",
    }
)

_CREATE_ORDER_TOOL_NAMES = frozenset(
    {
        "portfolio_write_create_order",
        "portfolio_write_create_orders",
    }
)

_ADD_CANDIDATE_TOOL_NAMES = frozenset(
    {
        "portfolio_write_add_candidate",
        "portfolio_write_add_candidates",
        "portfolio_write_add_holding",
        "portfolio_write_add_holdings",
    }
)

_PORTFOLIO_WRITE_TOOL_NAMES = frozenset(
    {
        "portfolio_write_create",
        "portfolio_write_rename",
        "portfolio_write_delete",
        *_ADD_CANDIDATE_TOOL_NAMES,
        *_CREATE_ORDER_TOOL_NAMES,
        *_SYNC_POSITION_TOOL_NAMES,
        "portfolio_write_remove_holding",
        "portfolio_write_remove_candidates",
        "portfolio_write_auto_allocate",
    }
)

_LIQUIDATE_RE = re.compile(
    r"(?:" r"全部清仓|清仓|全部卖出|全部卖掉|清掉|清空持仓|清掉持仓|" r"liquidate\s+all|close\s+all\s+(?:holdings|positions)|sell\s+all\s+(?:holdings|positions)" r")",
    re.IGNORECASE,
)

_PORTFOLIO_WRITE_ACTION_RE = re.compile(
    r"(?:"
    r"创建|新建|建立|构建|生成|添加|加入|移除|删除|剔除|重命名|改名|"
    r"买入|卖出|建仓|清仓|调仓|同步|"
    r"create|build|make|set\s*up|add|remove|delete|rename|"
    r"buy|sell|open|close|liquidate|rebalance|sync"
    r")",
    re.IGNORECASE,
)

_PORTFOLIO_WRITE_TARGET_RE = re.compile(
    r"(?:" r"投资组合|组合|候选池|自选股?|持仓|仓位|订单|股票池|" r"portfolio|watchlist|candidate|holding|position|order" r")",
    re.IGNORECASE,
)


def is_liquidation_intent(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    return bool(_LIQUIDATE_RE.search(text))


def has_explicit_portfolio_write_intent(message: str) -> bool:
    """Return whether the current user message explicitly requests a portfolio mutation."""

    text = (message or "").strip()
    if not text:
        return False
    return bool(_PORTFOLIO_WRITE_ACTION_RE.search(text) and _PORTFOLIO_WRITE_TARGET_RE.search(text))


def classify_portfolio_task(state: HarnessLoopState) -> PortfolioTaskKind:
    if _is_delete_only_task(state):
        return "delete"
    if not any(result.ok and result.name in _PORTFOLIO_WRITE_TOOL_NAMES for result in state.tool_results):
        return "none"
    if is_liquidation_intent(state.request.message) and state.any_ok_tool(*_CREATE_ORDER_TOOL_NAMES):
        return "liquidate"
    if state.any_ok_tool("portfolio_write_create") or state.any_ok_tool(*_ADD_CANDIDATE_TOOL_NAMES):
        return "build"
    if state.any_ok_tool(*_CREATE_ORDER_TOOL_NAMES) or state.any_ok_tool(*_SYNC_POSITION_TOOL_NAMES):
        return "trade"
    return "build"


def order_side_trace(state: HarnessLoopState) -> tuple[bool, bool]:
    """Return (has_ok_buy_orders, has_ok_sell_orders) from successful create_order tool results."""
    has_buy = False
    has_sell = False
    for result in state.tool_results:
        if not result.ok or result.name not in _CREATE_ORDER_TOOL_NAMES:
            continue
        data = result.data
        if not isinstance(data, dict):
            continue
        order_result = data.get("order_result")
        if not isinstance(order_result, dict):
            continue
        filled_orders = order_result.get("filled_orders")
        rows: list[Any]
        if isinstance(filled_orders, list) and filled_orders:
            rows = filled_orders
        else:
            rows = [order_result]
        for row in rows:
            if not isinstance(row, dict):
                continue
            side = str(row.get("order_side") or "").lower()
            if side == "buy":
                has_buy = True
            elif side == "sell":
                has_sell = True
    return has_buy, has_sell


def _is_delete_only_task(state: HarnessLoopState) -> bool:
    if not state.any_ok_tool("portfolio_write_delete"):
        return False
    mutating = {
        "portfolio_write_create",
        *_ADD_CANDIDATE_TOOL_NAMES,
        *_CREATE_ORDER_TOOL_NAMES,
        *_SYNC_POSITION_TOOL_NAMES,
        "portfolio_write_remove_holding",
        "portfolio_write_remove_candidates",
        "portfolio_write_auto_allocate",
    }
    if state.any_ok_tool(*mutating):
        return False
    for result in state.tool_results:
        if not result.ok or result.name not in _PORTFOLIO_WRITE_TOOL_NAMES:
            continue
        if result.name != "portfolio_write_delete":
            return False
    return True
