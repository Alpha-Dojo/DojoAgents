from __future__ import annotations

import json
from typing import Any

from dojoagents.dashboard.schemas.portfolio import (
    AddPortfolioHoldingRequest,
    AutoAllocateRequest,
    CreatePortfolioOrderRequest,
    CreatePortfolioRequest,
    RemovePortfolioHoldingRequest,
    UpdatePortfolioRequest,
)
from dojoagents.agent.escalation import AgentEscalationError
from dojoagents.agent.harnesses.portfolio_eval import (
    eval_summary_from_detail,
    parse_eval_submission,
    verify_eval_submission,
)
from dojoagents.dashboard.services.portfolio_order_preflight import preflight_buy_orders_from_detail
from dojoagents.dashboard.services.portfolio_order_resolution import resolve_portfolio_order_request
from dojoagents.dashboard.services.portfolio_service import PortfolioOrderFillError, PortfolioValidationError
from dojoagents.tools.registry import ToolRegistry, ToolSpec

_POSITION_ORDER_FIELDS = ("price", "cost", "qty", "order_time", "order_side")
_CANDIDATE_ONLY_ERROR = (
    "This tool adds WATCHLIST CANDIDATES (候选股) only — it does NOT buy shares or record cost. "
    "For 建仓/买入/按成本价/创建交易/持仓, use portfolio_write_create_order or "
    "portfolio_write_create_orders with order_side, price, qty, and optional order_time."
)


def _assert_candidate_only_fields(source: dict[str, Any], *, context: str) -> None:
    if any(source.get(field) is not None for field in _POSITION_ORDER_FIELDS):
        raise RuntimeError(f"{context}: {_CANDIDATE_ONLY_ERROR}")


def _normalize_market(market: str | None) -> str | None:
    if market is None:
        return None
    normalized = market.strip().lower()
    if normalized == "cn":
        return "sh"
    return normalized or None


def _service_or_raise(registry: FinancialDomainRegistry):
    service = registry.portfolio_service
    if service is None:
        raise RuntimeError("portfolio service is not ready")
    return service


def _json_content(
    payload: Any,
    *,
    resource_changes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "content": json.dumps(payload, ensure_ascii=False, indent=2),
        "data": payload,
        "resource_changes": list(resource_changes or []),
        "metadata": {"ok": True},
    }


def _resolve_buy_orders_for_preflight(
    registry,
    orders: list[CreatePortfolioOrderRequest],
) -> list[CreatePortfolioOrderRequest]:
    resolved: list[CreatePortfolioOrderRequest] = []
    for body in orders:
        if body.order_side != "buy":
            continue
        market = body.market
        if not market and registry.stock_store is not None:
            market = registry.stock_store.find_market(body.ticker)
        if not market:
            continue
        if market == body.market:
            resolved.append(body)
        else:
            resolved.append(body.model_copy(update={"market": market}))
    return resolved


async def _preflight_portfolio_buy_orders(
    registry,
    service,
    portfolio_id: str,
    orders: list[CreatePortfolioOrderRequest],
) -> None:
    buy_orders = _resolve_buy_orders_for_preflight(registry, orders)
    if not buy_orders:
        return
    detail = await service.get_detail(portfolio_id, include_performance=False)
    if detail is None:
        raise RuntimeError("portfolio not found")
    result = preflight_buy_orders_from_detail(detail.model_dump(), buy_orders)
    if result.ok:
        return
    raise AgentEscalationError(
        "capital_budget_exceeded",
        result.escalation_message(),
        context=result.escalation_context(),
        recoverable_by_agent=False,
    )


def register_dashboard_portfolio_tools(
    tool_registry: ToolRegistry,
    registry: FinancialDomainRegistry,
) -> None:
    async def list_portfolios(_: dict[str, Any]) -> dict[str, Any]:
        rows = await _service_or_raise(registry).list_summaries()
        return _json_content([row.model_dump() for row in rows])

    async def search_portfolios(args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query") or args.get("q") or "").strip()
        result = await _service_or_raise(registry).search(query)
        return _json_content(result.model_dump())

    async def get_portfolio_detail(args: dict[str, Any]) -> dict[str, Any]:
        portfolio_id = str(args.get("portfolio_id") or args.get("id") or "").strip()
        include_performance = bool(args.get("include_performance", True))
        detail = await _service_or_raise(registry).get_detail(
            portfolio_id,
            include_performance=include_performance,
        )
        if detail is None:
            raise RuntimeError("portfolio not found")
        payload = detail.model_dump()
        payload["eval_summary"] = eval_summary_from_detail(payload)
        return _json_content(payload)

    async def create_portfolio(args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("name") or "").strip()
        detail = await _service_or_raise(registry).create(
            CreatePortfolioRequest(name=name, kind="agent"),
        )
        payload = detail.model_dump()
        return _json_content(
            payload,
            resource_changes=[{"resource": "portfolio", "action": "create", "portfolio_id": payload.get("id")}],
        )

    async def rename_portfolio(args: dict[str, Any]) -> dict[str, Any]:
        portfolio_id = str(args.get("portfolio_id") or "").strip()
        name = str(args.get("name") or "").strip()
        detail = await _service_or_raise(registry).update(
            portfolio_id,
            UpdatePortfolioRequest(name=name),
        )
        if detail is None:
            raise RuntimeError("portfolio not found")
        payload = detail.model_dump()
        return _json_content(
            payload,
            resource_changes=[{"resource": "portfolio", "action": "rename", "portfolio_id": portfolio_id}],
        )

    async def delete_portfolio(args: dict[str, Any]) -> dict[str, Any]:
        portfolio_id = str(args.get("portfolio_id") or "").strip()
        try:
            ok = await _service_or_raise(registry).delete(portfolio_id, agent_only=True)
        except PortfolioValidationError as exc:
            raise RuntimeError(str(exc)) from exc
        if not ok:
            raise RuntimeError("portfolio not found")
        return _json_content(
            {"ok": True, "portfolio_id": portfolio_id},
            resource_changes=[{"resource": "portfolio", "action": "delete", "portfolio_id": portfolio_id}],
        )

    async def add_holding(args: dict[str, Any]) -> dict[str, Any]:
        _assert_candidate_only_fields(args, context="portfolio_write_add_candidate")
        portfolio_id = str(args.get("portfolio_id") or "").strip()
        body = AddPortfolioHoldingRequest(
            ticker=str(args.get("ticker") or "").strip(),
            market=_normalize_market(args.get("market")),
        )
        detail = await _service_or_raise(registry).add_holding(portfolio_id, body)
        if detail is None:
            raise RuntimeError("portfolio or ticker not found")
        payload = detail.model_dump()
        payload["add_result"] = {
            "added_to": "candidates",
            "candidate_count": len(detail.candidates),
            "candidate_count_by_market": eval_summary_from_detail(payload)["candidate_count_by_market"],
        }
        return _json_content(
            payload,
            resource_changes=[{"resource": "portfolio", "action": "add_candidate", "portfolio_id": portfolio_id}],
        )

    async def add_holdings_batch(args: dict[str, Any]) -> dict[str, Any]:
        portfolio_id = str(args.get("portfolio_id") or "").strip()
        holdings_raw = args.get("holdings")
        if not isinstance(holdings_raw, list) or not holdings_raw:
            raise RuntimeError("holdings must be a non-empty array")

        bodies: list[AddPortfolioHoldingRequest] = []
        for row in holdings_raw:
            if not isinstance(row, dict):
                continue
            _assert_candidate_only_fields(row, context="portfolio_write_add_candidates")
            bodies.append(
                AddPortfolioHoldingRequest(
                    ticker=str(row.get("ticker") or "").strip(),
                    market=_normalize_market(row.get("market")),
                )
            )
        if not bodies:
            raise RuntimeError("holdings must include at least one ticker")

        service = _service_or_raise(registry)
        before = await service.get_detail(portfolio_id, include_performance=False)
        before_keys = {
            (str(row.ticker).upper(), str(row.market))
            for row in (before.candidates if before else [])
        }

        detail = await service.add_holdings_batch(portfolio_id, bodies)
        if detail is None:
            raise RuntimeError("portfolio not found or no valid tickers in holdings")

        after_keys = {(str(row.ticker).upper(), str(row.market)) for row in detail.candidates}
        requested_keys: list[tuple[str, str | None]] = []
        for body in bodies:
            ticker = body.ticker.strip().upper()
            if not ticker:
                continue
            market = body.market or registry.stock_store.find_market(ticker) if registry.stock_store else None
            requested_keys.append((ticker, market))

        added_keys = after_keys - before_keys
        skipped_duplicates = [
            ticker
            for ticker, market in requested_keys
            if market and (ticker, market) in before_keys
        ]
        skipped_missing_market = [
            ticker for ticker, market in requested_keys if market is None
        ]

        payload = detail.model_dump()
        payload["add_result"] = {
            "added_to": "candidates",
            "requested": len(requested_keys),
            "added": len(added_keys),
            "skipped_duplicates": skipped_duplicates,
            "skipped_missing_market": skipped_missing_market,
            "candidate_count": len(detail.candidates),
            "candidate_count_by_market": eval_summary_from_detail(payload)["candidate_count_by_market"],
        }
        return _json_content(
            payload,
            resource_changes=[{"resource": "portfolio", "action": "add_candidate", "portfolio_id": portfolio_id}],
        )

    async def create_order(args: dict[str, Any]) -> dict[str, Any]:
        portfolio_id = str(args.get("portfolio_id") or "").strip()
        service = _service_or_raise(registry)
        body, resolution = await resolve_portfolio_order_request(registry, service, portfolio_id, args)
        if body.order_side == "buy":
            await _preflight_portfolio_buy_orders(registry, service, portfolio_id, [body])
        try:
            detail = await service.create_order(portfolio_id, body)
        except PortfolioOrderFillError as exc:
            raise RuntimeError(
                f"Order not filled ({exc.code}): {exc}. "
                "Adjust limit price (must be within the day's high/low), qty, order_time, or portfolio capital."
            ) from exc
        if detail is None:
            raise RuntimeError("portfolio or ticker not found")

        payload = detail.model_dump()
        summary = eval_summary_from_detail(payload)
        payload["order_result"] = {
            "ticker": body.ticker,
            "market": body.market,
            "order_side": body.order_side,
            "status": "filled",
            "price": body.price,
            "qty": body.qty,
            "order_time": body.order_time,
            "resolution": resolution.as_dict(),
            "position_count": summary["position_count"],
            "position_count_by_market": summary["position_count_by_market"],
        }
        return _json_content(
            payload,
            resource_changes=[{"resource": "portfolio", "action": "create_order", "portfolio_id": portfolio_id}],
        )

    async def create_orders_batch(args: dict[str, Any]) -> dict[str, Any]:
        portfolio_id = str(args.get("portfolio_id") or "").strip()
        orders_raw = args.get("orders")
        if not isinstance(orders_raw, list) or not orders_raw:
            raise RuntimeError("orders must be a non-empty array")

        filled: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        detail = None
        service = _service_or_raise(registry)

        bodies: list[CreatePortfolioOrderRequest] = []
        resolutions: list[dict[str, Any]] = []
        for row in orders_raw:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker") or "").strip()
            if not ticker:
                failed.append({"ticker": "", "error": "ticker is required"})
                continue
            order_side = str(row.get("order_side") or "buy").strip().lower()
            if order_side not in {"buy", "sell"}:
                failed.append({"ticker": ticker, "error": "order_side must be buy or sell"})
                continue
            try:
                body, resolution = await resolve_portfolio_order_request(
                    registry,
                    service,
                    portfolio_id,
                    row,
                )
            except AgentEscalationError:
                raise
            except RuntimeError as exc:
                failed.append({"ticker": ticker, "error": str(exc)})
                continue
            bodies.append(body)
            resolutions.append(resolution.as_dict())

        if not bodies:
            if failed:
                raise RuntimeError(f"No valid orders to place. Failures: {failed[:3]}")
            raise RuntimeError("orders must include at least one valid ticker")

        await _preflight_portfolio_buy_orders(registry, service, portfolio_id, bodies)

        for body, resolution in zip(bodies, resolutions):
            ticker = body.ticker
            order_side = body.order_side
            try:
                detail = await service.create_order(portfolio_id, body)
            except PortfolioOrderFillError as exc:
                failed.append(
                    {
                        "ticker": ticker,
                        "market": body.market,
                        "code": exc.code,
                        "error": str(exc),
                        "resolution": resolution,
                    }
                )
                continue
            if detail is None:
                failed.append({"ticker": ticker, "error": "portfolio or ticker not found"})
                continue
            filled.append(
                {
                    "ticker": ticker,
                    "market": body.market,
                    "order_side": order_side,
                    "status": "filled",
                    "price": body.price,
                    "qty": body.qty,
                    "order_time": body.order_time,
                    "resolution": resolution,
                }
            )

        if detail is None and not filled:
            raise RuntimeError("No orders were filled. Check price, qty, order_time, and portfolio capital.")

        if detail is None:
            detail = await service.get_detail(portfolio_id, include_performance=False)
        if detail is None:
            raise RuntimeError("portfolio not found")

        payload = detail.model_dump()
        summary = eval_summary_from_detail(payload)
        payload["order_result"] = {
            "requested": len(orders_raw),
            "filled": len(filled),
            "failed": failed,
            "filled_orders": filled,
            "position_count": summary["position_count"],
            "position_count_by_market": summary["position_count_by_market"],
        }
        return _json_content(
            payload,
            resource_changes=[{"resource": "portfolio", "action": "create_order", "portfolio_id": portfolio_id}],
        )

    async def remove_holding(args: dict[str, Any]) -> dict[str, Any]:
        portfolio_id = str(args.get("portfolio_id") or "").strip()
        body = RemovePortfolioHoldingRequest(
            ticker=str(args.get("ticker") or "").strip(),
            market=_normalize_market(args.get("market")),
        )
        detail = await _service_or_raise(registry).remove_holding(portfolio_id, body)
        if detail is None:
            raise RuntimeError("portfolio or holding not found")
        payload = detail.model_dump()
        return _json_content(
            payload,
            resource_changes=[{"resource": "portfolio", "action": "remove_holding", "portfolio_id": portfolio_id}],
        )

    async def auto_allocate(args: dict[str, Any]) -> dict[str, Any]:
        portfolio_id = str(args.get("portfolio_id") or "").strip()
        body = AutoAllocateRequest(market=_normalize_market(args.get("market")))
        detail = await _service_or_raise(registry).auto_allocate(portfolio_id, body)
        if detail is None:
            raise RuntimeError("portfolio not found")
        payload = detail.model_dump()
        return _json_content(
            payload,
            resource_changes=[{"resource": "portfolio", "action": "auto_allocate", "portfolio_id": portfolio_id}],
        )

    async def submit_eval(args: dict[str, Any]) -> dict[str, Any]:
        portfolio_id = str(args.get("portfolio_id") or "").strip()
        if not portfolio_id:
            raise RuntimeError("portfolio_id is required")
        min_by_market = args.get("min_candidates_by_market")
        if min_by_market is not None and not isinstance(min_by_market, dict):
            raise RuntimeError("min_candidates_by_market must be an object")
        min_positions_by_market = args.get("min_positions_by_market")
        if min_positions_by_market is not None and not isinstance(min_positions_by_market, dict):
            raise RuntimeError("min_positions_by_market must be an object")

        service = _service_or_raise(registry)
        detail = await service.get_detail(portfolio_id, include_performance=False)
        if detail is None:
            raise RuntimeError("portfolio not found")

        submission = parse_eval_submission(
            {
                "portfolio_id": portfolio_id,
                "task_summary": str(args.get("task_summary") or "").strip(),
                "require_kind_agent": bool(args.get("require_kind_agent", False)),
                "min_candidate_count": args.get("min_candidate_count"),
                "min_candidates_by_market": min_by_market,
                "min_position_count": args.get("min_position_count"),
                "min_positions_by_market": min_positions_by_market,
                "max_position_count": args.get("max_position_count"),
            }
        )
        if submission is None:
            raise RuntimeError("portfolio_id and task_summary are required")

        detail_payload = detail.model_dump()
        summary = eval_summary_from_detail(detail_payload)
        issues = verify_eval_submission(submission, detail_payload)
        if issues:
            raise RuntimeError(
                "Eval criteria not met: "
                + "; ".join(issues)
                + f". Actual candidates: total={summary['candidate_count']}, "
                f"by_market={summary['candidate_count_by_market']}. "
                f"Actual positions: total={summary['position_count']}, "
                f"by_market={summary['position_count_by_market']}. "
                "Use portfolio_read_detail eval_summary. "
                "For 建仓 tasks use portfolio_write_create_order(s) and min_position_count. "
                "For 清仓 tasks use max_position_count=0 and require_kind_agent=false. "
                "NOT portfolio_write_add_candidate(s)."
            )

        payload = {
            "portfolio_id": portfolio_id,
            "task_summary": submission.task_summary,
            "require_kind_agent": submission.require_kind_agent,
            "min_candidate_count": submission.min_candidate_count,
            "min_candidates_by_market": submission.min_candidates_by_market,
            "min_position_count": submission.min_position_count,
            "min_positions_by_market": submission.min_positions_by_market,
            "max_position_count": submission.max_position_count,
            "accepted": True,
            "eval_summary": summary,
        }
        return _json_content(payload)

    tool_specs = [
        ToolSpec(
            name="portfolio_read_list",
            description="List saved portfolios in the financial dashboard.",
            parameters={"type": "object", "properties": {}},
            handler=list_portfolios,
        ),
        ToolSpec(
            name="portfolio_read_search",
            description="Search portfolios by portfolio name or holding ticker/name.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
            handler=search_portfolios,
        ),
        ToolSpec(
            name="portfolio_read_detail",
            description=(
                "Fetch one portfolio detail. "
                "candidates = watchlist (候选股); positions/holdings = filled buys (持仓, from orders). "
                "eval_summary has candidate_count AND position_count — use the right metric for eval_submit. "
                "For 买入/卖出/减仓/清仓 order workflows set include_performance=false to keep the response small. "
                "When compressed to an artifact pointer, positions[] and eval_summary remain visible. "
                "Required verification step after any portfolio write."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "include_performance": {"type": "boolean"},
                },
                "required": ["portfolio_id"],
            },
            handler=get_portfolio_detail,
        ),
        ToolSpec(
            name="portfolio_eval_submit",
            description=(
                "Submit portfolio task success criteria AFTER portfolio_read_detail. "
                "Watchlist tasks: min_candidate_count. "
                "建仓/买入 tasks: min_position_count (filled positions from create_order). "
                "清仓/liquidation tasks: max_position_count=0, require_kind_agent=false. "
                "Set require_kind_agent=true ONLY when portfolio_write_create was used in this run. "
                "Never use min_candidate_count to verify 建仓 — candidates ≠ positions."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "task_summary": {
                        "type": "string",
                        "description": "One-line summary of what the user asked for and what you did.",
                    },
                    "require_kind_agent": {
                        "type": "boolean",
                        "description": "Set true ONLY when you used portfolio_write_create in this run.",
                    },
                    "min_candidate_count": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Minimum watchlist candidates — NOT for 建仓 tasks.",
                    },
                    "min_candidates_by_market": {
                        "type": "object",
                        "description": "Optional per-market candidate minimums, e.g. {\"us\": 5}.",
                        "additionalProperties": {"type": "integer", "minimum": 0},
                    },
                    "min_position_count": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Minimum filled positions (持仓) after create_order — use for 建仓 tasks.",
                    },
                    "min_positions_by_market": {
                        "type": "object",
                        "description": "Optional per-market position minimums for 建仓, e.g. {\"us\": 3}.",
                        "additionalProperties": {"type": "integer", "minimum": 0},
                    },
                    "max_position_count": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "Maximum filled positions after sell — use 0 for 清仓/liquidation tasks.",
                    },
                },
                "required": ["portfolio_id", "task_summary"],
            },
            handler=submit_eval,
        ),
        ToolSpec(
            name="portfolio_write_create",
            description=(
                "Create a new DojoAgent-generated portfolio. "
                "Always use this for user create-portfolio tasks; portfolios are tagged kind=agent (DojoAgent 生成). "
                "Never delete a portfolio in the same create/build workflow."
            ),
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            handler=create_portfolio,
        ),
        ToolSpec(
            name="portfolio_write_rename",
            description="Rename an existing portfolio.",
            parameters={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "name": {"type": "string"},
                },
                "required": ["portfolio_id", "name"],
            },
            handler=rename_portfolio,
        ),
        ToolSpec(
            name="portfolio_write_delete",
            description=(
                "Delete a DojoAgent-generated portfolio ONLY when the user explicitly asks to delete. "
                "After success, optionally call portfolio_read_list to confirm it is gone. "
                "Do NOT call portfolio_read_detail or portfolio_eval_submit after delete — the portfolio no longer exists."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                },
                "required": ["portfolio_id"],
            },
            handler=delete_portfolio,
        ),
        ToolSpec(
            name="portfolio_write_add_candidate",
            description=(
                "Add ONE ticker to the portfolio WATCHLIST (候选股). "
                "Does NOT buy shares, spend capital, or set cost — no price/qty/order_time. "
                "For 建仓/买入/按成本价, use portfolio_write_create_order instead."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "ticker": {"type": "string"},
                    "market": {"type": "string", "description": "us, cn, or hk"},
                },
                "required": ["portfolio_id", "ticker"],
            },
            handler=add_holding,
        ),
        ToolSpec(
            name="portfolio_write_add_candidates",
            description=(
                "Add multiple tickers to the portfolio WATCHLIST (候选股) in one batch. "
                "Does NOT buy or 建仓. Response add_result.added_to is always candidates. "
                "For 建仓 with cost/qty, use portfolio_write_create_orders."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "holdings": {
                        "type": "array",
                        "description": "Candidate tickers only (ticker + market). No price/qty.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "ticker": {"type": "string"},
                                "market": {"type": "string"},
                            },
                            "required": ["ticker"],
                        },
                        "minItems": 1,
                    },
                },
                "required": ["portfolio_id", "holdings"],
            },
            handler=add_holdings_batch,
        ),
        ToolSpec(
            name="portfolio_write_add_holding",
            description=(
                "Alias for portfolio_write_add_candidate — adds WATCHLIST candidate only, NOT a filled position. "
                "Prefer portfolio_write_add_candidate. For 建仓 use portfolio_write_create_order."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "ticker": {"type": "string"},
                    "market": {"type": "string"},
                },
                "required": ["portfolio_id", "ticker"],
            },
            handler=add_holding,
        ),
        ToolSpec(
            name="portfolio_write_add_holdings",
            description=(
                "Alias for portfolio_write_add_candidates — WATCHLIST batch only, NOT 建仓. "
                "Prefer portfolio_write_add_candidates. For 建仓 use portfolio_write_create_orders."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "holdings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "ticker": {"type": "string"},
                                "market": {"type": "string"},
                            },
                            "required": ["ticker"],
                        },
                        "minItems": 1,
                    },
                },
                "required": ["portfolio_id", "holdings"],
            },
            handler=add_holdings_batch,
        ),
        ToolSpec(
            name="portfolio_write_create_order",
            description=(
                "Buy or sell to create/update a REAL position (持仓/建仓/清仓). "
                "Provide ticker + order_side; price/qty/order_time are optional — the server resolves defaults: "
                "no date + no price -> latest daily close; order_time only -> that day's open; "
                "price only -> latest trading day when price fits that bar, else nearest historical match; "
                "price + order_time -> validate price within that day's [low, high] inclusive. "
                "When using a realtime quote price, also pass order_time from the latest kline datetime. "
                "no qty on buy -> 10% of available market cash (lot-normalized); "
                "no qty on sell -> if user asked 清仓/全部卖出, sell all held shares; otherwise ask the user "
                "(suggest 50%, 75%, 100% via qty_pct). "
                "US qty must be whole shares; HK/A-share qty must be multiples of 100."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "ticker": {"type": "string"},
                    "market": {"type": "string", "description": "us, cn, or hk"},
                    "order_side": {"type": "string", "enum": ["buy", "sell"]},
                    "price": {
                        "type": "number",
                        "description": (
                            "Optional limit price; must be within order_time day's [low, high] inclusive. "
                            "When sourced from realtime quote, pass order_time too."
                        ),
                    },
                    "qty": {
                        "type": "number",
                        "description": "Optional shares; US integer, HK/A-share multiple of 100",
                    },
                    "qty_pct": {
                        "type": "number",
                        "description": "Optional sell fraction of held shares (0-1), e.g. 0.5 for 50%",
                    },
                    "liquidate_all": {
                        "type": "boolean",
                        "description": "When true on sell, default qty to all held shares for this ticker",
                    },
                    "order_time": {
                        "type": "string",
                        "description": (
                            "Optional execution date YYYY-MM-DD. Recommended when passing a quote-derived price."
                        ),
                    },
                },
                "required": ["portfolio_id", "ticker", "order_side"],
            },
            handler=create_order,
        ),
        ToolSpec(
            name="portfolio_write_create_orders",
            description=(
                "Batch buy/sell orders. Each row needs ticker + order_side; "
                "price/qty/order_time optional with the same server-side resolution rules as create_order. "
                "For 清仓, omit qty on sell rows when the user asked to liquidate all — server fills held shares. "
                "Preflight checks capital budget and order validity before any fill."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "orders": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "ticker": {"type": "string"},
                                "market": {"type": "string"},
                                "order_side": {"type": "string", "enum": ["buy", "sell"]},
                                "price": {"type": "number"},
                                "qty": {"type": "number"},
                                "qty_pct": {
                                    "type": "number",
                                    "description": "Optional sell fraction of held shares (0-1)",
                                },
                                "liquidate_all": {
                                    "type": "boolean",
                                    "description": "Sell all held shares for this ticker",
                                },
                                "order_time": {"type": "string"},
                            },
                            "required": ["ticker", "order_side"],
                        },
                        "minItems": 1,
                    },
                },
                "required": ["portfolio_id", "orders"],
            },
            handler=create_orders_batch,
        ),
        ToolSpec(
            name="portfolio_write_remove_holding",
            description="Remove one ticker from the portfolio WATCHLIST (候选股). Does not close a filled position — use create_order with order_side=sell for that.",
            parameters={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "ticker": {"type": "string"},
                    "market": {"type": "string"},
                },
                "required": ["portfolio_id", "ticker"],
            },
            handler=remove_holding,
        ),
        ToolSpec(
            name="portfolio_write_auto_allocate",
            description="Auto allocate a portfolio by market-cap weighting.",
            parameters={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "market": {"type": "string"},
                },
                "required": ["portfolio_id"],
            },
            handler=auto_allocate,
        ),
    ]

    for spec in tool_specs:
        tool_registry.register(spec)
