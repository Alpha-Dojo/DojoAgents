from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timezone
from typing import Callable, List, Optional

from dojoagents.dashboard.services.portfolio_allocation import (
    allocate_market_cap_weighted,
    holding_uses_default_open_date,
    lookup_open_price,
    resolve_cost_date,
)
from dojoagents.dashboard.services.portfolio_order_execution import (
    aggregate_positions_bounded,
    evaluate_order_fill_failure,
    market_tickers_from_orders,
    process_pending_orders,
    replay_market_balance,
    sanitize_invalid_filled_orders,
)
from dojoagents.dashboard.services.portfolio_store import MARKETS, PortfolioStore
from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.services.kline_bar_utils import (
    DATA_START_DATE,
    KLINE_MAX_LIMIT,
    resolve_kline_limit_for_elapsed_days,
)
from dojoagents.dashboard.services.market_stats import display_valuation_ratio
from dojoagents.dashboard.services.stock_sector_store import StockSectorStore
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.schemas.portfolio import (
    AddPortfolioHoldingRequest,
    AutoAllocateRequest,
    CancelPortfolioOrderRequest,
    CreatePortfolioOrderRequest,
    CreatePortfolioRequest,
    PortfolioCapitalConfig,
    PortfolioCandidateView,
    PortfolioDetail,
    PortfolioHoldingView,
    PortfolioOrderView,
    PortfolioPerformanceView,
    PortfolioPositionView,
    PortfolioSearchItem,
    PortfolioSearchResponse,
    RemovePortfolioHoldingRequest,
    PortfolioSummary,
    SyncPortfolioPositionsRequest,
    UpdatePortfolioRequest,
)
from dojoagents.dashboard.schemas.stock_kline import ConstituentKlineBatchResponse
from dojoagents.dashboard.services.market_sector_lead import _stock_bilingual_name
from dojoagents.dashboard.services.portfolio_performance import (
    build_candidate_index_performance,
    build_market_performance,
)
from dojoagents.dashboard.services.portfolio_performance_cache import (
    PortfolioPerformanceCache,
    performance_cache_key,
    portfolio_content_fingerprint,
)
from dojoagents.dashboard.services.portfolio_candidate_index import (
    build_candidate_index_series_by_market,
)

DEFAULT_BENCHMARKS = {"us": "^SPX", "sh": "000001.SS", "hk": "^HSI"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class PortfolioValidationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        field: str,
        context: Optional[dict] = None,
    ) -> None:
        super().__init__(message)
        self.field = field
        self.context = context or {}


class PortfolioOrderFillError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        order_id: str,
        code: str = "not_filled",
        context: Optional[dict] = None,
    ) -> None:
        super().__init__(message)
        self.order_id = order_id
        self.code = code
        self.context = context or {}


def _stock_display_name(stock) -> str:
    if stock.short_name:
        return str(stock.short_name)
    if stock.long_name:
        return str(stock.long_name)
    quote = stock.stock_quote
    if quote and quote.name:
        return quote.name
    return stock.ticker


async def _stock_sector_label(stock_sector_store: StockSectorStore, market: str, ticker: str, stock) -> str:
    sector = stock_sector_store.get(market, ticker)
    if sector and sector.primary.level_1.zh:
        return sector.primary.level_1.zh
    if sector and sector.primary.level_1.en:
        return sector.primary.level_1.en
    if stock.sector:
        return str(stock.sector)
    if stock.industry:
        return str(stock.industry)
    return ""


def _normalize_config(raw: Optional[dict]) -> Optional[PortfolioCapitalConfig]:
    if not isinstance(raw, dict):
        return None
    payload = dict(raw)
    if not payload.get("cost_date") and payload.get("start_date"):
        payload["cost_date"] = payload["start_date"]
    return PortfolioCapitalConfig.model_validate(payload)


def _resolve_kline_limit(raw: dict) -> int:
    config = raw.get("config") if isinstance(raw.get("config"), dict) else {}
    start = str(config.get("start_date") or "")[:10]
    if not start:
        return KLINE_MAX_LIMIT
    return resolve_kline_limit_for_elapsed_days(start)


def _config_capital_by_market(raw: dict) -> Optional[dict]:
    config = raw.get("config")
    if not isinstance(config, dict):
        return None
    capital = config.get("capital_by_market")
    return capital if isinstance(capital, dict) else None


def _has_open_position_for_candidate(
    positions: list[dict],
    *,
    ticker: str,
    market: Optional[str],
) -> bool:
    for row in positions:
        if str(row.get("ticker")) != ticker:
            continue
        if float(row.get("shares") or 0) <= 0:
            continue
        if market is None or str(row.get("market")) == market:
            return True
    return False


def _market_initial_capital(config: Optional[dict], market: str) -> float:
    capital = (config or {}).get("capital_by_market") or {}
    if not isinstance(capital, dict):
        return 0.0
    if market in capital:
        return float(capital[market] or 0)
    if market == "sh" and "cn" in capital:
        return float(capital["cn"] or 0)
    return float(capital.get(market) or 0)


def _portfolio_start_date(config: Optional[dict], orders: list[dict]) -> str:
    if isinstance(config, dict) and config.get("start_date"):
        return str(config["start_date"])[:10]
    from dojoagents.dashboard.services.portfolio_order_execution import market_filled_orders

    dates = []
    for market in MARKETS:
        for order in market_filled_orders(orders, market=market):
            fill_date = str(order.get("fill_time") or order.get("order_time") or order.get("created_at") or "")[:10]
            if fill_date:
                dates.append(fill_date)
    if dates:
        return min(dates)
    from dojoagents.dashboard.services.portfolio_store import DEFAULT_PORTFOLIO_START_DATE

    return DEFAULT_PORTFOLIO_START_DATE


def _closes_from_kline_bars(bars: list, *, chart_start: str) -> dict[str, float]:
    return {
        bar.bar_time[:10]: float(bar.close)
        for bar in bars
        if bar.close > 0 and bar.bar_time[:10] >= chart_start
    }


def _collect_performance_tickers(
    orders: list[dict],
    candidate_rows: list[dict],
) -> list[str]:
    tickers: set[str] = set()
    for market in MARKETS:
        tickers.update(market_tickers_from_orders(orders, market=market))
    for row in candidate_rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip()
        if ticker:
            tickers.add(ticker)
    return sorted(tickers)


def _ticker_closes_by_market_from_batch(
    orders: list[dict],
    kline_batch: ConstituentKlineBatchResponse,
    *,
    chart_start: str,
) -> dict[str, dict[str, dict[str, float]]]:
    tickers_by_market = {
        market: market_tickers_from_orders(orders, market=market) for market in MARKETS
    }
    ticker_closes_by_market: dict[str, dict[str, dict[str, float]]] = {
        market: {} for market in MARKETS
    }
    for market in MARKETS:
        for ticker in tickers_by_market[market]:
            kline = kline_batch.items.get(ticker)
            if kline is None or not kline.bars:
                continue
            closes = _closes_from_kline_bars(kline.bars, chart_start=chart_start)
            if closes:
                ticker_closes_by_market[market][ticker] = closes
    return ticker_closes_by_market


class PortfolioService:
    def __init__(
        self,
        store: PortfolioStore,
        stock_store: StockStore,
        stock_sector_store: StockSectorStore,
        kline_store: KlineStore,
        benchmark_store=None,
        *,
        market_data_revision_reader: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.stock_store = stock_store
        self.stock_sector_store = stock_sector_store
        self.kline_store = kline_store
        self.benchmark_store = benchmark_store
        self._market_data_revision_reader = market_data_revision_reader
        self._performance_cache = PortfolioPerformanceCache()

    async def _store_call(self, method_name: str, *args, **kwargs):
        method = getattr(self.store, method_name)
        return await asyncio.to_thread(method, *args, **kwargs)

    async def list_summaries(self) -> List[PortfolioSummary]:
        rows = await self._store_call("list_index_rows")
        return [self._to_summary(row) for row in rows]

    async def get_detail(
        self,
        portfolio_id: str,
        *,
        include_performance: bool = True,
        benchmark_by_market: Optional[dict[str, str]] = None,
    ) -> Optional[PortfolioDetail]:
        raw = await self._store_call("get_raw", portfolio_id)
        if not raw:
            return None
        raw = await self._ensure_orders_processed(portfolio_id, raw)
        raw = await self._ensure_position_candidates(portfolio_id, raw)
        detail = await self._to_detail(raw)
        if not include_performance:
            return detail.model_copy(update={"performance": None})
        performance = await self._build_performance(
            raw,
            portfolio_id=portfolio_id,
            benchmark_by_market=benchmark_by_market,
        )
        return detail.model_copy(update={"performance": performance})

    async def get_performance(
        self,
        portfolio_id: str,
        *,
        benchmark_by_market: Optional[dict[str, str]] = None,
        start_date: Optional[str] = None,
    ) -> Optional[PortfolioPerformanceView]:
        raw = await self._store_call("get_raw", portfolio_id)
        if not raw:
            return None
        raw = await self._ensure_orders_processed(portfolio_id, raw)
        raw = await self._ensure_position_candidates(portfolio_id, raw)
        if start_date:
            config = raw.get("config") if isinstance(raw.get("config"), dict) else {}
            raw = {
                **raw,
                "config": {
                    **config,
                    "start_date": start_date,
                },
            }
        return await self._build_performance(
            raw,
            portfolio_id=portfolio_id,
            benchmark_by_market=benchmark_by_market,
        )

    async def create(self, body: CreatePortfolioRequest) -> PortfolioDetail:
        raw = await self._store_call("create", body.name, kind=body.kind)
        detail = await self._to_detail(raw)
        if detail is None:
            raise RuntimeError("failed to create portfolio")
        return detail

    async def update(self, portfolio_id: str, body: UpdatePortfolioRequest) -> Optional[PortfolioDetail]:
        raw_before = await self._store_call("get_raw", portfolio_id)
        if not raw_before:
            return None
        if body.kind is not None:
            current_kind = str(raw_before.get("kind") or "manual")
            if body.kind == "agent" and current_kind != "agent":
                raise PortfolioValidationError(
                    "user-built portfolios cannot be converted to DojoAgent-generated",
                    field="kind",
                )
            if body.kind == "manual" and current_kind not in {"agent", "manual"}:
                raise PortfolioValidationError("invalid portfolio kind transition", field="kind")
        await self._validate_cost_overrides(raw_before, body)
        config = body.config.model_dump() if body.config is not None else None
        if isinstance(config, dict) and not config.get("cost_date") and config.get("start_date"):
            config["cost_date"] = config["start_date"]
        raw = await self._store_call(
            "update",
            portfolio_id,
            name=body.name,
            kind=body.kind,
            pinned=body.pinned,
            config=config,
            shares_by_ticker=body.shares_by_ticker,
            manual_shares_by_ticker=body.manual_shares_by_ticker,
            open_date_by_ticker=body.open_date_by_ticker,
            shares_locked_by_ticker=body.shares_locked_by_ticker,
            open_date_locked_by_ticker=body.open_date_locked_by_ticker,
            cost_locked_by_ticker=body.cost_locked_by_ticker,
            cost_override_by_ticker=body.cost_override_by_ticker,
        )
        if not raw:
            return None
        return await self._to_detail(raw)

    async def _validate_cost_overrides(
        self,
        raw: dict,
        body: UpdatePortfolioRequest,
    ) -> None:
        overrides = body.cost_override_by_ticker
        if not overrides:
            return
        holdings = {str(row.get("ticker")): row for row in raw.get("candidates") or [] if isinstance(row, dict) and row.get("ticker")}
        config = raw.get("config") if isinstance(raw.get("config"), dict) else None
        for ticker, cost in overrides.items():
            if cost is None:
                continue
            row = holdings.get(ticker)
            if row is None:
                continue
            unlock_cost = body.cost_locked_by_ticker is not None and body.cost_locked_by_ticker.get(ticker) is False
            if bool(row.get("cost_locked", False)) and not unlock_cost:
                continue

            requested_open = body.open_date_by_ticker.get(ticker) if body.open_date_by_ticker is not None and ticker in body.open_date_by_ticker else None
            unlock_open = body.open_date_locked_by_ticker is not None and body.open_date_locked_by_ticker.get(ticker) is False
            if bool(row.get("open_date_locked", False)) and not unlock_open:
                requested_open = None
            open_date = str(requested_open).strip()[:10] if requested_open else resolve_cost_date(row, config)
            field = f"cost_override_by_ticker.{ticker}"
            if not open_date:
                raise PortfolioValidationError(
                    "open date is required before setting cost override",
                    field=field,
                )
            try:
                date.fromisoformat(open_date)
            except ValueError as exc:
                raise PortfolioValidationError(
                    "invalid open date",
                    field=f"open_date_by_ticker.{ticker}",
                ) from exc

            market = str(row.get("market") or self.stock_store.find_market(ticker) or "")
            kline = await self.kline_store.get_or_fetch_kline(
                ticker,
                market=market or None,
                start_time=open_date,
                end_time=open_date,
                limit=1,
            )
            if kline is None or not kline.bars:
                raise PortfolioValidationError(
                    f"kline is unavailable for {ticker} on {open_date}",
                    field=field,
                )
            bar = next(
                (item for item in kline.bars if item.bar_time[:10] == open_date),
                None,
            )
            if bar is None:
                raise PortfolioValidationError(
                    f"kline is unavailable for {ticker} on {open_date}",
                    field=field,
                )
            low = float(bar.low)
            high = float(bar.high)
            value = float(cost)
            if value < low or value > high:
                raise PortfolioValidationError(
                    "cost override is outside the open-day kline range",
                    field=field,
                    context={"low": low, "high": high},
                )

    async def delete(self, portfolio_id: str, *, agent_only: bool = False) -> bool:
        if agent_only:
            raw = await self._store_call("get_raw", portfolio_id)
            if not raw:
                return False
            if str(raw.get("kind") or "manual") != "agent":
                raise PortfolioValidationError(
                    "only DojoAgent-generated portfolios can be deleted by the agent; "
                    "user-built portfolios are protected",
                    field="kind",
                )
        return await self._store_call("delete", portfolio_id)

    async def add_holding(self, portfolio_id: str, body: AddPortfolioHoldingRequest) -> Optional[PortfolioDetail]:
        ticker = body.ticker.strip()
        market = body.market or self.stock_store.find_market(ticker)
        if not market:
            return None

        raw = await self._store_call("add_candidate", portfolio_id, ticker=ticker, market=market)
        if not raw:
            return None
        return await self._to_detail(raw)

    async def add_candidate(self, portfolio_id: str, body: AddPortfolioHoldingRequest) -> Optional[PortfolioDetail]:
        return await self.add_holding(portfolio_id, body)

    async def add_holdings_batch(
        self,
        portfolio_id: str,
        bodies: list[AddPortfolioHoldingRequest],
    ) -> Optional[PortfolioDetail]:
        entries: list[tuple[str, str]] = []
        skipped_missing_market: list[str] = []
        for body in bodies:
            ticker = body.ticker.strip()
            if not ticker:
                continue
            market = body.market or self.stock_store.find_market(ticker)
            if not market:
                skipped_missing_market.append(ticker)
                continue
            entries.append((ticker, market))

        if not entries and skipped_missing_market:
            return None

        if not entries:
            return None

        raw = await self._store_call("add_candidates_batch", portfolio_id, entries=entries)
        if not raw:
            return None
        return await self._to_detail(raw)

    async def create_order(
        self,
        portfolio_id: str,
        body: CreatePortfolioOrderRequest,
    ) -> Optional[PortfolioDetail]:
        ticker = body.ticker.strip()
        market = body.market or self.stock_store.find_market(ticker)
        if not market:
            return None
        stock = self.stock_store.get(market, ticker)
        if stock is None:
            return None

        order_id = str(uuid.uuid4())
        order = {
            "id": order_id,
            "ticker": ticker,
            "market": market,
            "order_side": body.order_side,
            "order_status": "pending",
            "price": float(body.price),
            "qty": float(body.qty),
            "order_time": body.order_time,
            "fill_time": None,
            "fill_price": None,
            "created_at": _utc_now_iso(),
            "updated_at": None,
        }
        if body.resolved_bar is not None:
            order["resolved_bar"] = body.resolved_bar.model_dump()
        raw = await self._store_call("add_order", portfolio_id, order=order)
        if not raw:
            return None
        config_raw = raw.get("config") if isinstance(raw.get("config"), dict) else {}
        initial_capital = _market_initial_capital(config_raw, market)
        raw = await self._ensure_orders_processed(portfolio_id, raw)
        orders = [row for row in raw.get("orders") or [] if isinstance(row, dict)]
        saved = next((row for row in orders if str(row.get("id")) == order_id), None)
        if saved is None:
            return await self._to_detail(raw)

        status = str(saved.get("order_status") or "")
        if status == "filled":
            capital_by_market = _config_capital_by_market({"config": config_raw}) if config_raw else None
            positions = aggregate_positions_bounded(
                orders,
                capital_by_market=capital_by_market,
            )
            has_position = any(
                str(row.get("market")) == market
                and str(row.get("ticker")) == ticker
                and float(row.get("shares") or 0) > 0
                for row in positions
            )
            if body.order_side == "buy" and not has_position:
                await self._discard_order(portfolio_id, order_id, orders)
                raise PortfolioOrderFillError(
                    "order filled but position was not created",
                    order_id=order_id,
                )
            raw = await self._ensure_position_candidates(portfolio_id, raw)
            return await self._to_detail(raw)

        failure = await evaluate_order_fill_failure(
            saved,
            kline_store=self.kline_store,
            prior_orders=[row for row in orders if str(row.get("id")) != order_id],
            initial_capital=initial_capital,
        )
        await self._discard_order(portfolio_id, order_id, orders)
        raise PortfolioOrderFillError(
            failure.message if failure is not None else "order was not filled",
            order_id=order_id,
            code=failure.code if failure is not None else "not_filled",
            context={
                **(failure.context if failure is not None else {}),
                "order_status": status,
            },
        )

    async def sync_positions(
        self,
        portfolio_id: str,
        body: SyncPortfolioPositionsRequest,
    ) -> Optional[PortfolioDetail]:
        raw = await self._store_call("get_raw", portfolio_id)
        if not raw:
            return None

        synced_at = str(body.synced_at or _utc_now_iso()).strip() or _utc_now_iso()
        source = str(body.source).strip() if body.source else None
        note = str(body.note).strip() if body.note else None

        for index, item in enumerate(body.items):
            ticker = item.ticker.strip()
            if not ticker:
                raise PortfolioValidationError("ticker is required", field=f"items[{index}].ticker")
            market = item.market or self.stock_store.find_market(ticker)
            if not market:
                raise PortfolioValidationError(
                    f"market not found for {ticker}",
                    field=f"items[{index}].market",
                )
            stock = self.stock_store.get(market, ticker)
            if stock is None:
                raise PortfolioValidationError(
                    f"ticker not found: {ticker}",
                    field=f"items[{index}].ticker",
                )
            qty = float(item.qty)
            if qty > 1e-9 and (item.cost is None or float(item.cost) <= 0):
                raise PortfolioValidationError(
                    "cost is required when qty > 0",
                    field=f"items[{index}].cost",
                )

            fill_price = float(item.cost) if qty > 1e-9 else 0.0
            order = {
                "id": str(uuid.uuid4()),
                "ticker": ticker,
                "market": market,
                "order_kind": "sync",
                "order_side": "set",
                "order_status": "filled",
                "price": fill_price if fill_price > 0 else 1.0,
                "qty": qty,
                "order_time": None,
                "fill_time": synced_at,
                "fill_price": fill_price if fill_price > 0 else None,
                "created_at": synced_at,
                "updated_at": synced_at,
                "source": source,
                "sync_note": note,
            }
            raw = await self._store_call("add_order", portfolio_id, order=order)
            if not raw:
                return None

        raw = await self._ensure_position_candidates(portfolio_id, raw)
        return await self._to_detail(raw)

    async def cancel_order(
        self,
        portfolio_id: str,
        body: CancelPortfolioOrderRequest,
    ) -> Optional[PortfolioDetail]:
        raw = await self._store_call("cancel_order", portfolio_id, order_id=body.order_id.strip())
        if not raw:
            return None
        return await self._to_detail(raw)

    async def _ensure_position_candidates(self, portfolio_id: str, raw: dict) -> dict:
        positions = aggregate_positions_bounded(
            [row for row in raw.get("orders") or [] if isinstance(row, dict)],
            capital_by_market=_config_capital_by_market(raw),
        )
        candidates = raw.get("candidates") or []
        existing = {
            (str(row.get("market")), str(row.get("ticker")))
            for row in candidates
            if isinstance(row, dict) and row.get("ticker") and row.get("market")
        }
        updated = raw
        for row in positions:
            if float(row.get("shares") or 0) <= 0:
                continue
            key = (str(row.get("market")), str(row.get("ticker")))
            if key in existing:
                continue
            added = await self._store_call(
                "add_candidate",
                portfolio_id,
                ticker=str(row.get("ticker")),
                market=str(row.get("market")),
            )
            if added:
                updated = added
                existing.add(key)
        return updated

    async def _ensure_orders_processed(self, portfolio_id: str, raw: dict) -> dict:
        orders = [row for row in raw.get("orders") or [] if isinstance(row, dict)]
        capital_by_market = _config_capital_by_market(raw)
        sanitized, changed_sanitize = sanitize_invalid_filled_orders(
            orders,
            capital_by_market=capital_by_market,
        )
        processed = await process_pending_orders(
            sanitized,
            kline_store=self.kline_store,
            initial_capital_by_market=capital_by_market,
        )
        if not changed_sanitize and processed == sanitized:
            return raw
        saved = await self._store_call("save_orders", portfolio_id, processed)
        return saved or {**raw, "orders": processed}

    async def _discard_order(
        self,
        portfolio_id: str,
        order_id: str,
        orders: list[dict],
    ) -> None:
        remaining = [row for row in orders if str(row.get("id")) != order_id]
        await self._store_call("save_orders", portfolio_id, remaining)

    async def remove_holding(
        self,
        portfolio_id: str,
        body: RemovePortfolioHoldingRequest,
    ) -> Optional[PortfolioDetail]:
        raw = await self._store_call("get_raw", portfolio_id)
        if not raw:
            return None
        raw = await self._ensure_orders_processed(portfolio_id, raw)
        ticker = body.ticker.strip()
        market = body.market
        positions = aggregate_positions_bounded(
            [row for row in raw.get("orders") or [] if isinstance(row, dict)],
            capital_by_market=_config_capital_by_market(raw),
        )
        if any(
            str(row.get("market")) == market
            and str(row.get("ticker")) == ticker
            and float(row.get("shares") or 0) > 0
            for row in positions
        ):
            raise PortfolioValidationError(
                "cannot remove candidate while position is open",
                field=f"candidates.{ticker}",
            )

        raw = await self._store_call(
            "remove_holding",
            portfolio_id,
            ticker=ticker,
            market=market,
        )
        if not raw:
            return None
        return await self._to_detail(raw)

    async def remove_holdings_batch(
        self,
        portfolio_id: str,
        bodies: list[RemovePortfolioHoldingRequest],
    ) -> tuple[Optional[PortfolioDetail], list[str]]:
        raw = await self._store_call("get_raw", portfolio_id)
        if not raw:
            return None, []
        raw = await self._ensure_orders_processed(portfolio_id, raw)
        positions = aggregate_positions_bounded(
            [row for row in raw.get("orders") or [] if isinstance(row, dict)],
            capital_by_market=_config_capital_by_market(raw),
        )

        blocked_open_position: list[str] = []
        entries: list[tuple[str, Optional[str]]] = []
        for body in bodies:
            ticker = body.ticker.strip()
            if not ticker:
                continue
            market = body.market
            if _has_open_position_for_candidate(positions, ticker=ticker, market=market):
                blocked_open_position.append(ticker)
                continue
            entries.append((ticker, market))

        if blocked_open_position and not entries:
            raise PortfolioValidationError(
                "cannot remove candidate while position is open",
                field=f"candidates.{blocked_open_position[0]}",
            )

        if not entries:
            detail = await self._to_detail(raw)
            return detail, blocked_open_position

        raw = await self._store_call("remove_candidates_batch", portfolio_id, entries=entries)
        if not raw:
            return None, blocked_open_position
        detail = await self._to_detail(raw)
        return detail, blocked_open_position

    async def auto_allocate(self, portfolio_id: str, body: AutoAllocateRequest) -> Optional[PortfolioDetail]:
        del body
        raw = await self._store_call("get_raw", portfolio_id)
        if not raw:
            return None
        return await self._to_detail(raw)

    async def search(self, query: str) -> PortfolioSearchResponse:
        normalized = query.strip().lower()
        if not normalized:
            return PortfolioSearchResponse(query=query, items=[])

        hits: list[PortfolioSearchItem] = []
        seen: set[str] = set()

        index_rows = await self._store_call("list_index_rows")
        for row in index_rows:
            portfolio_id = str(row["id"])
            name = str(row.get("name") or "")
            if normalized in name.lower():
                hits.append(PortfolioSearchItem(id=portfolio_id, match_type="name"))
                seen.add(portfolio_id)

        for row in index_rows:
            portfolio_id = str(row["id"])
            if portfolio_id in seen:
                continue
            raw = await self._store_call("get_raw", portfolio_id)
            if not raw:
                continue
            for holding in raw.get("candidates") or []:
                if not isinstance(holding, dict):
                    continue
                ticker = str(holding.get("ticker") or "")
                market = str(holding.get("market") or "")
                stock = self.stock_store.get(market, ticker)
                display_name = _stock_display_name(stock) if stock else ticker
                if normalized in ticker.lower() or normalized in display_name.lower():
                    hits.append(
                        PortfolioSearchItem(
                            id=portfolio_id,
                            match_type="candidate",
                            matched_ticker=ticker,
                            matched_name=display_name,
                        )
                    )
                    seen.add(portfolio_id)
                    break

        return PortfolioSearchResponse(query=query, items=hits)

    def _to_summary(self, row: dict) -> PortfolioSummary:
        return PortfolioSummary(
            id=str(row["id"]),
            name=str(row.get("name") or row["id"]),
            subtitle=row.get("subtitle"),
            kind=row.get("kind") or "manual",
            pinned=bool(row.get("pinned", False)),
            today_change=None,
            net_value_usd=None,
        )

    async def _to_detail(self, raw: dict) -> PortfolioDetail:
        summary = self._to_summary(raw)
        parsed_config = _normalize_config(raw.get("config"))
        config_raw = raw.get("config") if isinstance(raw.get("config"), dict) else None
        candidates = await self._build_candidates(raw.get("candidates") or [])
        order_rows = [row for row in raw.get("orders") or [] if isinstance(row, dict)]
        position_rows = aggregate_positions_bounded(
            order_rows,
            capital_by_market=_config_capital_by_market(raw),
        )
        positions = await self._build_positions(position_rows, config_raw)
        orders = self._build_order_views(raw.get("orders") or [])
        as_of_date = date.today().isoformat()
        net_value_by_market = {"us": 0.0, "sh": 0.0, "hk": 0.0}
        cost_basis_by_market = {"us": 0.0, "sh": 0.0, "hk": 0.0}
        for holding in positions:
            cost_basis_by_market[holding.market] = cost_basis_by_market.get(holding.market, 0.0) + holding.cost_basis
        for market in MARKETS:
            initial_capital = _market_initial_capital(config_raw, market)
            cash, held = replay_market_balance(
                order_rows,
                market=market,
                initial_capital=initial_capital,
                as_of_date=as_of_date,
            )
            position_value = 0.0
            for ticker, shares in held.items():
                stock = self.stock_store.get(market, ticker)
                quote = stock.stock_quote if stock else None
                if quote is not None and quote.last_price > 0:
                    position_value += shares * float(quote.last_price)
                    continue
                for row in positions:
                    if row.market == market and row.ticker == ticker:
                        position_value += shares * float(row.price)
                        break
            net_value_by_market[market] = cash + position_value

        total_nav = sum(net_value_by_market.values())
        if total_nav > 0:
            positions = [
                item.model_copy(update={"weight": (item.market_value / total_nav) * 100.0})
                for item in positions
            ]

        return PortfolioDetail(
            **summary.model_dump(),
            config=parsed_config,
            candidates=candidates,
            positions=positions,
            orders=orders,
            holdings=positions,
            kpis=None,
            performance=None,
            net_value_by_market=net_value_by_market,
            cost_basis_by_market=cost_basis_by_market,
        )

    async def _load_order_ticker_closes_by_market(
        self,
        orders: list[dict],
        *,
        chart_start: str,
        kline_limit: int,
        kline_batch: ConstituentKlineBatchResponse | None = None,
    ) -> dict[str, dict[str, dict[str, float]]]:
        if kline_batch is not None:
            return _ticker_closes_by_market_from_batch(
                orders,
                kline_batch,
                chart_start=chart_start,
            )

        tickers_by_market = {
            market: market_tickers_from_orders(orders, market=market) for market in MARKETS
        }
        all_tickers = sorted({ticker for tickers in tickers_by_market.values() for ticker in tickers})
        ticker_closes_by_market: dict[str, dict[str, dict[str, float]]] = {
            market: {} for market in MARKETS
        }
        if not all_tickers:
            return ticker_closes_by_market

        batch = await self.kline_store.get_klines(all_tickers, limit=kline_limit)
        return _ticker_closes_by_market_from_batch(orders, batch, chart_start=chart_start)

    async def _build_performance(
        self,
        raw: dict,
        *,
        portfolio_id: str = "",
        benchmark_by_market: Optional[dict[str, str]] = None,
    ) -> Optional[PortfolioPerformanceView]:
        if self.benchmark_store is None:
            return None
        resolved_benchmarks = {
            market: (benchmark_by_market or {}).get(market) or DEFAULT_BENCHMARKS[market]
            for market in MARKETS
        }
        config = raw.get("config") if isinstance(raw.get("config"), dict) else {}
        start_date = _portfolio_start_date(config, [row for row in raw.get("orders") or [] if isinstance(row, dict)])
        revision = ""
        if self._market_data_revision_reader is not None:
            revision = str(self._market_data_revision_reader() or "")
        cache_key = performance_cache_key(
            portfolio_id=portfolio_id or str(raw.get("id") or ""),
            fingerprint=portfolio_content_fingerprint(raw),
            start_date=start_date,
            benchmark_by_market=resolved_benchmarks,
            market_data_revision=revision,
        )
        cached = self._performance_cache.get(cache_key)
        if cached is not None:
            return cached

        kline_limit = _resolve_kline_limit(raw)
        chart_start = start_date if start_date >= DATA_START_DATE else DATA_START_DATE
        orders = [row for row in raw.get("orders") or [] if isinstance(row, dict)]
        candidate_rows = [row for row in raw.get("candidates") or [] if isinstance(row, dict)]
        performance_tickers = _collect_performance_tickers(orders, candidate_rows)
        kline_batch = (
            await self.kline_store.get_klines(performance_tickers, limit=kline_limit)
            if performance_tickers
            else ConstituentKlineBatchResponse(items={})
        )

        ticker_closes_by_market = await self._load_order_ticker_closes_by_market(
            orders,
            chart_start=chart_start,
            kline_limit=kline_limit,
            kline_batch=kline_batch,
        )
        benchmark_closes_by_market: dict[str, dict[str, float]] = {}
        calendar: set[str] = set()

        for market in MARKETS:
            benchmark_symbol = resolved_benchmarks[market]
            benchmark = await self.benchmark_store.get_kline(benchmark_symbol, limit=kline_limit)
            if benchmark is None or not benchmark.bars:
                continue
            benchmark_closes = {bar.bar_time[:10]: float(bar.close) for bar in benchmark.bars}
            benchmark_closes_by_market[market] = benchmark_closes
            calendar.update(day for day in benchmark_closes if day >= start_date)
            for closes in ticker_closes_by_market.get(market, {}).values():
                calendar.update(day for day in closes if day >= start_date)

        calendar_dates = sorted(calendar)

        async def build_market_series(market: str):
            initial_capital = _market_initial_capital(config, market)
            tickers = market_tickers_from_orders(orders, market=market)
            if initial_capital <= 0 and not tickers:
                return None
            benchmark_closes = benchmark_closes_by_market.get(market)
            if not benchmark_closes or len(calendar_dates) < 2:
                return None
            benchmark_symbol = resolved_benchmarks[market]
            result = build_market_performance(
                market=market,
                orders=orders,
                initial_capital=initial_capital,
                start_date=start_date,
                ticker_closes=ticker_closes_by_market.get(market) or {},
                benchmark_symbol=benchmark_symbol,
                benchmark_closes=benchmark_closes,
                calendar_dates=calendar_dates,
            )
            if result.dates:
                return market, result
            return None

        series = {}
        for built in await asyncio.gather(*(build_market_series(market) for market in MARKETS)):
            if built is None:
                continue
            market, result = built
            series[market] = result

        candidate_raw = await build_candidate_index_series_by_market(
            candidates=candidate_rows,
            stock_store=self.stock_store,
            kline_store=self.kline_store,
            kline_batch=kline_batch,
        )
        candidate_series_by_market: dict[str, list[dict]] = {}
        candidate_stats_by_market: dict = {}
        candidate_market_perf: dict[str, PortfolioMarketPerformance] = {}

        async def build_candidate_market_series(market: str):
            points = candidate_raw.get(market)
            if not points or len(points) < 2:
                return None
            benchmark_symbol = resolved_benchmarks[market]
            benchmark = await self.benchmark_store.get_kline(benchmark_symbol, limit=kline_limit)
            if benchmark is None or not benchmark.bars:
                return None
            benchmark_closes = {bar.bar_time[:10]: float(bar.close) for bar in benchmark.bars}
            index_by_date = {str(point["date"]): float(point["value"]) for point in points}
            result = build_candidate_index_performance(
                market=market,
                index_by_date=index_by_date,
                benchmark_symbol=benchmark_symbol,
                benchmark_closes=benchmark_closes,
            )
            if not result.dates:
                return None
            return market, result, points

        for built in await asyncio.gather(*(build_candidate_market_series(market) for market in MARKETS)):
            if built is None:
                continue
            market, result, points = built
            candidate_market_perf[market] = result
            candidate_series_by_market[market] = [
                {"date": day, "value": float(value)}
                for day, value in zip(result.dates, result.portfolio)
            ]
            candidate_stats_by_market[market] = result.stats

        if not series and not candidate_market_perf:
            return None
        ordered = [series[market] for market in MARKETS if market in series]
        if ordered:
            primary = ordered[0]
            starts = [item.dates[0] for item in ordered if item.dates]
            ends = [item.dates[-1] for item in ordered if item.dates]
            window_start = min(starts) if starts else None
            window_end = max(ends) if ends else None
        else:
            primary = next(iter(candidate_market_perf.values()))
            window_start = primary.dates[0] if primary.dates else None
            window_end = primary.dates[-1] if primary.dates else None

        benchmark_by_market = {market: item.benchmark for market, item in series.items()}
        benchmark_symbol_by_market = {
            market: item.benchmark_symbol for market, item in series.items()
        }
        for market, item in candidate_market_perf.items():
            if not benchmark_by_market.get(market):
                benchmark_by_market[market] = item.benchmark
            if market not in benchmark_symbol_by_market:
                benchmark_symbol_by_market[market] = item.benchmark_symbol

        performance = PortfolioPerformanceView(
            dates=primary.dates,
            portfolio=primary.portfolio,
            benchmark=primary.benchmark,
            window_start=window_start,
            window_end=window_end,
            series_by_market=series,
            candidate_series_by_market=candidate_series_by_market,
            benchmark_by_market=benchmark_by_market,
            benchmark_symbol_by_market=benchmark_symbol_by_market,
            stats_by_market={market: item.stats for market, item in series.items()},
            candidate_stats_by_market=candidate_stats_by_market,
        )
        self._performance_cache.set(cache_key, performance)
        return performance

    async def _build_candidates(self, rows: list) -> List[PortfolioCandidateView]:
        candidates: list[PortfolioCandidateView] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker") or "")
            market = str(row.get("market") or "")
            stock = self.stock_store.get(market, ticker)
            if stock is None:
                candidates.append(
                    PortfolioCandidateView(
                        ticker=ticker,
                        name=ticker,
                        market=market,
                    )
                )
                continue
            quote = stock.stock_quote
            price = float(quote.last_price) if quote else 0.0
            change_percent = float(quote.change_percent) if quote else 0.0
            market_cap = float(quote.market_cap) if quote else 0.0
            pe = display_valuation_ratio(float(quote.pe) if quote else None)
            pb = display_valuation_ratio(float(quote.pb) if quote else None)
            dividend_yield = float(quote.dividend_yield) if quote else None
            turn_rate = float(quote.turn_rate) if quote else None
            eps = (price / pe) if pe and pe > 0 else None
            sector_label = await _stock_sector_label(self.stock_sector_store, market, ticker, stock)
            sector = self.stock_sector_store.get(market, ticker)
            level_1 = level_2 = level_3 = ""
            if sector is not None:
                level_1 = sector.primary.level_1.zh or sector.primary.level_1.en
                level_2 = sector.primary.level_2.zh or sector.primary.level_2.en
                level_3 = sector.primary.level_3.zh or sector.primary.level_3.en
            display_name = _stock_display_name(stock)
            bilingual = _stock_bilingual_name(stock)
            candidates.append(
                PortfolioCandidateView(
                    ticker=ticker,
                    name=display_name,
                    name_zh=bilingual.zh,
                    name_en=bilingual.en,
                    market=market,
                    price=price,
                    change_percent=change_percent,
                    market_cap=market_cap,
                    pe=pe,
                    pb=pb,
                    dividend_yield=dividend_yield,
                    eps=eps,
                    turn_rate=turn_rate,
                    sector=sector_label,
                    sector_l1=level_1,
                    sector_l2=level_2,
                    sector_l3=level_3,
                )
            )
        return candidates

    def _build_order_views(self, rows: list) -> List[PortfolioOrderView]:
        views: list[PortfolioOrderView] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("order_status") or "") == "rejected":
                continue
            ticker = str(row.get("ticker") or "")
            market = str(row.get("market") or "")
            stock = self.stock_store.get(market, ticker)
            display_name = _stock_display_name(stock) if stock else ticker
            bilingual = _stock_bilingual_name(stock) if stock else None
            views.append(
                PortfolioOrderView(
                    id=str(row.get("id") or ""),
                    ticker=ticker,
                    market=market,
                    order_side=str(row.get("order_side") or "buy"),
                    order_kind=str(row.get("order_kind") or "trade"),
                    order_status=str(row.get("order_status") or "pending"),
                    price=float(row.get("price") or 0),
                    qty=float(row.get("qty") or 0),
                    order_time=row.get("order_time"),
                    fill_time=row.get("fill_time"),
                    fill_price=float(row["fill_price"]) if row.get("fill_price") is not None else None,
                    created_at=str(row.get("created_at") or ""),
                    updated_at=row.get("updated_at"),
                    source=row.get("source"),
                    sync_note=row.get("sync_note"),
                    name=display_name,
                    name_zh=bilingual.zh if bilingual else "",
                    name_en=bilingual.en if bilingual else "",
                )
            )
        return views

    async def _build_positions(self, rows: list, config_raw: Optional[dict]) -> List[PortfolioPositionView]:
        del config_raw
        positions: list[PortfolioPositionView] = []

        for row in rows:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker") or "")
            market = str(row.get("market") or "")
            shares = float(row.get("shares") or 0.0)
            if shares <= 0:
                continue
            stock = self.stock_store.get(market, ticker)
            if stock is None:
                continue
            quote = stock.stock_quote
            price = float(quote.last_price) if quote else 0.0
            change_percent = float(quote.change_percent) if quote else 0.0
            cost = float(row.get("cost") or 0.0)
            cost_basis = float(row.get("cost_basis") or cost * shares)
            open_date = row.get("open_date")
            market_value = price * shares
            sector_label = await _stock_sector_label(self.stock_sector_store, market, ticker, stock)
            sector = self.stock_sector_store.get(market, ticker)
            level_1 = level_2 = level_3 = ""
            if sector is not None:
                level_1 = sector.primary.level_1.zh or sector.primary.level_1.en
                level_2 = sector.primary.level_2.zh or sector.primary.level_2.en
                level_3 = sector.primary.level_3.zh or sector.primary.level_3.en
            display_name = _stock_display_name(stock)
            bilingual = _stock_bilingual_name(stock)
            total_return_pct = ((price - cost) / cost * 100.0) if cost > 0 and price > 0 else None
            view = PortfolioPositionView(
                ticker=ticker,
                name=display_name,
                name_zh=bilingual.zh,
                name_en=bilingual.en,
                market=market,
                shares=shares,
                weight=0.0,
                cost=cost,
                uses_default_cost=False,
                cost_basis=cost_basis,
                open_date=str(open_date) if open_date else None,
                uses_default_open_date=False,
                manual_shares=False,
                shares_locked=True,
                open_date_locked=True,
                cost_locked=True,
                price=price,
                change_percent=change_percent,
                sector=sector_label,
                sector_l1=level_1,
                sector_l2=level_2,
                sector_l3=level_3,
                market_value=market_value,
            )
            if total_return_pct is not None:
                view = view.model_copy(update={})
            positions.append(view)

        return positions
