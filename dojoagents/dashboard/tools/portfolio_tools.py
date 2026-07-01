from __future__ import annotations

import json
from typing import Any

from dojoagents.dashboard.schemas.portfolio import (
    AddPortfolioHoldingRequest,
    AutoAllocateRequest,
    CreatePortfolioRequest,
    RemovePortfolioHoldingRequest,
    UpdatePortfolioRequest,
)
from dojoagents.agent.harnesses.portfolio_eval import (
    eval_summary_from_detail,
    parse_eval_submission,
    verify_eval_submission,
)
from dojoagents.dashboard.services.portfolio_service import PortfolioValidationError
from dojoagents.tools.registry import ToolRegistry, ToolSpec


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
        portfolio_id = str(args.get("portfolio_id") or "").strip()
        body = AddPortfolioHoldingRequest(
            ticker=str(args.get("ticker") or "").strip(),
            market=_normalize_market(args.get("market")),
            shares=float(args["shares"]) if args.get("shares") is not None else None,
        )
        detail = await _service_or_raise(registry).add_holding(portfolio_id, body)
        if detail is None:
            raise RuntimeError("portfolio or ticker not found")
        payload = detail.model_dump()
        return _json_content(
            payload,
            resource_changes=[{"resource": "portfolio", "action": "add_holding", "portfolio_id": portfolio_id}],
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
            bodies.append(
                AddPortfolioHoldingRequest(
                    ticker=str(row.get("ticker") or "").strip(),
                    market=_normalize_market(row.get("market")),
                    shares=float(row["shares"]) if row.get("shares") is not None else None,
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
            "requested": len(requested_keys),
            "added": len(added_keys),
            "skipped_duplicates": skipped_duplicates,
            "skipped_missing_market": skipped_missing_market,
            "candidate_count": len(detail.candidates),
            "candidate_count_by_market": eval_summary_from_detail(payload)["candidate_count_by_market"],
        }
        return _json_content(
            payload,
            resource_changes=[{"resource": "portfolio", "action": "add_holding", "portfolio_id": portfolio_id}],
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
                + f". Actual: total={summary['candidate_count']}, "
                f"by_market={summary['candidate_count_by_market']}. "
                "Use portfolio_read_detail eval_summary for counts. "
                "Do NOT invent stricter min_candidates_by_market than actual counts. "
                "If short, add NEW tickers (check add_result.skipped_duplicates); "
                "do not re-add existing symbols or unrelated names."
            )

        payload = {
            "portfolio_id": portfolio_id,
            "task_summary": submission.task_summary,
            "require_kind_agent": submission.require_kind_agent,
            "min_candidate_count": submission.min_candidate_count,
            "min_candidates_by_market": submission.min_candidates_by_market,
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
                "Fetch one portfolio detail (candidates, kind, config). "
                "Response includes eval_summary with candidate_count_by_market — "
                "use these ACTUAL counts for portfolio_eval_submit. "
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
                "Submit portfolio build success criteria AFTER portfolio_read_detail. "
                "min_candidate_count / min_candidates_by_market must NOT exceed eval_summary actual counts. "
                "Only set per-market minimums when the user explicitly required them. "
                "Returns accepted=true only when criteria match the portfolio; otherwise fix and retry."
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
                        "description": "Set true when you used portfolio_write_create (DojoAgent-generated).",
                    },
                    "min_candidate_count": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Minimum total candidates required for success.",
                    },
                    "min_candidates_by_market": {
                        "type": "object",
                        "description": "Optional per-market minimums, e.g. {\"us\": 5} or {\"us\": 1, \"cn\": 1, \"hk\": 1}.",
                        "additionalProperties": {"type": "integer", "minimum": 0},
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
            name="portfolio_write_add_holding",
            description=(
                "Add one ticker to a portfolio candidate pool. "
                "When adding multiple tickers, prefer portfolio_write_add_holdings in one batch."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "ticker": {"type": "string"},
                    "market": {"type": "string"},
                    "shares": {"type": "number"},
                },
                "required": ["portfolio_id", "ticker"],
            },
            handler=add_holding,
        ),
        ToolSpec(
            name="portfolio_write_add_holdings",
            description=(
                "Add multiple tickers to a portfolio candidate pool in one atomic batch. "
                "Response includes add_result: added count, skipped_duplicates, candidate_count_by_market. "
                "Duplicates do not increase count — add NEW tickers only when topping up."
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
                                "shares": {"type": "number"},
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
            name="portfolio_write_remove_holding",
            description="Remove one holding from a portfolio.",
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
