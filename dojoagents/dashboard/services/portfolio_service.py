from __future__ import annotations

import asyncio
from datetime import date
from typing import List, Optional

from dojoagents.dashboard.services.portfolio_allocation import (
    allocate_market_cap_weighted,
    holding_uses_default_open_date,
    initial_shares_for_new_holding,
    lookup_open_price,
    resolve_cost_date,
)
from dojoagents.dashboard.services.portfolio_store import MARKETS, PortfolioStore
from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.services.stock_sector_store import StockSectorStore
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.schemas.portfolio import (
    AddPortfolioHoldingRequest,
    AutoAllocateRequest,
    CreatePortfolioRequest,
    PortfolioCapitalConfig,
    PortfolioDetail,
    PortfolioHoldingView,
    PortfolioPerformanceView,
    PortfolioSearchItem,
    PortfolioSearchResponse,
    RemovePortfolioHoldingRequest,
    PortfolioSummary,
    UpdatePortfolioRequest,
)
from dojoagents.dashboard.services.portfolio_performance import build_market_performance

DEFAULT_BENCHMARKS = {"us": "^SPX", "sh": "000001.SS", "hk": "^HSI"}


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


class PortfolioService:
    def __init__(
        self,
        store: PortfolioStore,
        stock_store: StockStore,
        stock_sector_store: StockSectorStore,
        kline_store: KlineStore,
        benchmark_store=None,
    ) -> None:
        self.store = store
        self.stock_store = stock_store
        self.stock_sector_store = stock_sector_store
        self.kline_store = kline_store
        self.benchmark_store = benchmark_store

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
        detail = await self._to_detail(raw)
        if not include_performance:
            return detail.model_copy(update={"performance": None})
        performance = await self._build_performance(raw, benchmark_by_market=benchmark_by_market)
        return detail.model_copy(update={"performance": performance})

    async def create(self, body: CreatePortfolioRequest) -> PortfolioDetail:
        raw = await self._store_call("create", body.name)
        detail = await self._to_detail(raw)
        if detail is None:
            raise RuntimeError("failed to create portfolio")
        return detail

    async def update(self, portfolio_id: str, body: UpdatePortfolioRequest) -> Optional[PortfolioDetail]:
        raw_before = await self._store_call("get_raw", portfolio_id)
        if not raw_before:
            return None
        await self._validate_cost_overrides(raw_before, body)
        config = body.config.model_dump() if body.config is not None else None
        if isinstance(config, dict) and not config.get("cost_date") and config.get("start_date"):
            config["cost_date"] = config["start_date"]
        raw = await self._store_call(
            "update",
            portfolio_id,
            name=body.name,
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
        holdings = {str(row.get("ticker")): row for row in raw.get("holdings") or [] if isinstance(row, dict) and row.get("ticker")}
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

    async def delete(self, portfolio_id: str) -> bool:
        return await self._store_call("delete", portfolio_id)

    async def add_holding(self, portfolio_id: str, body: AddPortfolioHoldingRequest) -> Optional[PortfolioDetail]:
        ticker = body.ticker.strip()
        market = body.market or self.stock_store.find_market(ticker)
        if not market:
            return None

        raw = await self._store_call("get_raw", portfolio_id)
        if not raw:
            return None

        config = raw.get("config") if isinstance(raw.get("config"), dict) else {}
        capital_map = config.get("capital_by_market") if isinstance(config.get("capital_by_market"), dict) else {}
        capital = float(capital_map.get(market) or 0.0)

        if body.shares is not None and body.shares > 0:
            shares = float(body.shares)
        else:
            shares = float(
                await initial_shares_for_new_holding(
                    self.stock_store,
                    raw.get("holdings") or [],
                    market,
                    ticker,
                    capital,
                )
            )

        raw = await self._store_call(
            "add_holding",
            portfolio_id,
            ticker=ticker,
            market=market,
            shares=shares,
        )
        if not raw:
            return None
        return await self._to_detail(raw)

    async def remove_holding(
        self,
        portfolio_id: str,
        body: RemovePortfolioHoldingRequest,
    ) -> Optional[PortfolioDetail]:
        raw = await self._store_call(
            "remove_holding",
            portfolio_id,
            ticker=body.ticker.strip(),
            market=body.market,
        )
        if not raw:
            return None
        return await self._to_detail(raw)

    async def auto_allocate(self, portfolio_id: str, body: AutoAllocateRequest) -> Optional[PortfolioDetail]:
        raw = await self._store_call("get_raw", portfolio_id)
        if not raw:
            return None

        config = raw.get("config") if isinstance(raw.get("config"), dict) else {}
        capital_map = config.get("capital_by_market") if isinstance(config.get("capital_by_market"), dict) else {}
        markets = [body.market] if body.market else list(MARKETS)

        shares_by_ticker: dict[str, float] = {}
        for market in markets:
            if market not in MARKETS:
                continue
            capital = float(capital_map.get(market) or 0.0)
            allocated = await allocate_market_cap_weighted(
                self.stock_store,
                raw.get("holdings") or [],
                market,
                capital,
                skip_manual=True,
            )
            shares_by_ticker.update({ticker: float(value) for ticker, value in allocated.items()})

        if not shares_by_ticker:
            return await self._to_detail(raw)

        raw = await self._store_call("apply_market_shares", portfolio_id, shares_by_ticker, reset_manual=False)
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
            for holding in raw.get("holdings") or []:
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
                            match_type="holding",
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
        holdings = await self._build_holdings(raw.get("holdings") or [], config_raw)
        net_value_by_market = {"us": 0.0, "sh": 0.0, "hk": 0.0}
        cost_basis_by_market = {"us": 0.0, "sh": 0.0, "hk": 0.0}
        for holding in holdings:
            net_value_by_market[holding.market] = net_value_by_market.get(holding.market, 0.0) + holding.market_value
            cost_basis_by_market[holding.market] = cost_basis_by_market.get(holding.market, 0.0) + holding.cost_basis

        return PortfolioDetail(
            **summary.model_dump(),
            config=parsed_config,
            holdings=holdings,
            kpis=None,
            performance=None,
            net_value_by_market=net_value_by_market,
            cost_basis_by_market=cost_basis_by_market,
        )

    async def _build_performance(
        self,
        raw: dict,
        *,
        benchmark_by_market: Optional[dict[str, str]] = None,
    ) -> Optional[PortfolioPerformanceView]:
        if self.benchmark_store is None:
            return None
        by_market: dict[str, list[dict]] = {market: [] for market in MARKETS}
        holdings_rows = [row for row in raw.get("holdings") or [] if isinstance(row, dict)]

        async def build_holding_series(row: dict) -> tuple[str, dict] | None:
            if not isinstance(row, dict):
                return None
            market = str(row.get("market") or "")
            ticker = str(row.get("ticker") or "")
            shares = float(row.get("shares") or 0)
            if market not in by_market or not ticker or shares <= 0:
                return None
            kline = await self.kline_store.get_or_fetch_kline(ticker, market=market, kline_t="1D", limit=252)
            if kline is None or not kline.bars:
                return None
            return market, {
                "shares": shares,
                "closes": {bar.bar_time[:10]: float(bar.close) for bar in kline.bars},
            }

        for built in await asyncio.gather(*(build_holding_series(row) for row in holdings_rows)):
            if built is None:
                continue
            market, series = built
            by_market[market].append(series)

        async def build_market_series(market: str):
            holdings = by_market.get(market) or []
            if not holdings:
                return None
            benchmark_symbol = (benchmark_by_market or {}).get(market) or DEFAULT_BENCHMARKS[market]
            benchmark = await self.benchmark_store.get_kline(benchmark_symbol, limit=252)
            if benchmark is None or not benchmark.bars:
                return None
            benchmark_closes = {bar.bar_time[:10]: float(bar.close) for bar in benchmark.bars}
            result = build_market_performance(
                market=market,
                holdings=holdings,
                benchmark_symbol=benchmark_symbol,
                benchmark_closes=benchmark_closes,
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

        if not series:
            return None
        ordered = [series[market] for market in MARKETS if market in series]
        primary = ordered[0]
        starts = [item.dates[0] for item in ordered if item.dates]
        ends = [item.dates[-1] for item in ordered if item.dates]
        return PortfolioPerformanceView(
            dates=primary.dates,
            portfolio=primary.portfolio,
            benchmark=primary.benchmark,
            window_start=min(starts) if starts else None,
            window_end=max(ends) if ends else None,
            series_by_market=series,
            benchmark_by_market={market: item.benchmark for market, item in series.items()},
            benchmark_symbol_by_market={market: item.benchmark_symbol for market, item in series.items()},
            stats_by_market={market: item.stats for market, item in series.items()},
        )

    async def _build_holdings(self, rows: list, config_raw: Optional[dict]) -> List[PortfolioHoldingView]:
        holdings: list[PortfolioHoldingView] = []
        total_value = 0.0
        built: list[tuple[PortfolioHoldingView, float]] = []

        for row in rows:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker") or "")
            market = str(row.get("market") or "")
            shares = float(row.get("shares") or 0.0)
            manual_shares = bool(row.get("manual_shares"))
            stock = self.stock_store.get(market, ticker)
            if stock is None:
                continue
            quote = stock.stock_quote
            price = float(quote.last_price) if quote else 0.0
            change_percent = float(quote.change_percent) if quote else 0.0
            open_date = resolve_cost_date(row, config_raw)
            open_price = lookup_open_price(self.kline_store, ticker, open_date) if open_date else None
            cost = float(open_price) if open_price and open_price > 0 else price
            cost_override = row.get("cost_override")
            if cost_override is not None:
                cost = float(cost_override)
            market_value = price * shares
            total_value += market_value
            sector_label = await _stock_sector_label(self.stock_sector_store, market, ticker, stock)
            sector = self.stock_sector_store.get(market, ticker)
            level_1 = ""
            level_2 = ""
            level_3 = ""
            if sector is not None:
                level_1 = sector.primary.level_1.zh or sector.primary.level_1.en
                level_2 = sector.primary.level_2.zh or sector.primary.level_2.en
                level_3 = sector.primary.level_3.zh or sector.primary.level_3.en
            display_name = _stock_display_name(stock)
            view = PortfolioHoldingView(
                ticker=ticker,
                name=display_name,
                name_zh=str(stock.short_name or display_name),
                name_en=str(stock.long_name or display_name),
                market=market,
                shares=shares,
                weight=0.0,
                cost=cost,
                uses_default_cost=cost_override is None,
                cost_basis=cost * shares,
                open_date=open_date,
                uses_default_open_date=holding_uses_default_open_date(row),
                manual_shares=manual_shares,
                shares_locked=bool(row.get("shares_locked", manual_shares)),
                open_date_locked=bool(row.get("open_date_locked", False)),
                cost_locked=bool(row.get("cost_locked", False)),
                price=price,
                change_percent=change_percent,
                sector=sector_label,
                sector_l1=level_1,
                sector_l2=level_2,
                sector_l3=level_3,
                market_value=market_value,
            )
            built.append((view, market_value))

        if total_value > 0:
            holdings = [view.model_copy(update={"weight": (value / total_value) * 100.0}) for view, value in built]
        else:
            holdings = [view for view, _ in built]

        by_market: dict[str, list[PortfolioHoldingView]] = {"us": [], "sh": [], "hk": []}
        for view in holdings:
            by_market.setdefault(view.market, []).append(view)

        weighted: list[PortfolioHoldingView] = []
        for market in ("us", "sh", "hk"):
            rows = by_market.get(market, [])
            market_total = sum(row.market_value for row in rows)
            if market_total > 0:
                weighted.extend(row.model_copy(update={"weight": (row.market_value / market_total) * 100.0}) for row in rows)
            else:
                weighted.extend(rows)

        return weighted
