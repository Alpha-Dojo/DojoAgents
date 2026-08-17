from __future__ import annotations

from typing import Any

from dojoagents.dashboard.services.market_stats import display_valuation_ratio
from dojoagents.dashboard.services.market_sector_lead import _stock_bilingual_name
from dojoagents.dashboard.services.sector_constituents import MARKETS, SectorLevel
from dojoagents.dashboard.services.sector_store import ResolvedSectorPath
from dojoagents.dashboard.services.constituent_filter import (
    stock_is_equity_quote_type,
    stock_is_us_warrant_by_name,
)
from dojoagents.dashboard.services.stock_quote_filter import stock_passes_ticker_market_cap_min
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.services.domain_utils import finite_float
from dojoagents.dashboard.services.market_window import resolve_market_analysis_window
from dojoagents.dashboard.schemas.dojo_sphere import SectorConstituentItem, SectorConstituentsResponse

CURRENCY_BY_MARKET = {"us": "USD", "sh": "CNY", "hk": "HKD"}
VALID_QUERY_MARKETS = {"cn", *MARKETS}


def _market_candidates(market: str | None) -> list[str | None]:
    if market is None:
        return [None]
    code = str(market).strip().lower()
    if code == "cn":
        return ["cn", "sh"]
    if code == "sh":
        return ["sh", "cn"]
    return [code]


def _ticker_return_map(
    sector_precomputed_store: Any,
    tickers: list[str],
    *,
    days: int | None,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, float]:
    start = str(start_date or "").strip() or None
    end = str(end_date or "").strip() or None
    if start and end:
        window = resolve_market_analysis_window(start_date=start, end_date=end)
        rows = sector_precomputed_store.get_ticker_daily_for_window(window, tickers)
        if not rows:
            raise ValueError(f"No trading data available between {start} and {end}.")
        return {str(row["ticker"]): finite_float(row.get("daily_return_pct")) for row in rows if row.get("ticker")}

    window_days = days if days and days > 0 else 365
    rows = sector_precomputed_store.get_ticker_daily_by_window(window_days, tickers)
    return {str(row["ticker"]): finite_float(row.get("daily_return_pct")) for row in rows if row.get("ticker")}


async def list_sector_constituents(
    stock_store: StockStore,
    sector_precomputed_store: Any,
    path: ResolvedSectorPath,
    *,
    scope: SectorLevel = "L3",
    market: str | None = None,
    days: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> SectorConstituentsResponse:
    """Constituents for L1/L2/L3 scope of the selected sector path."""
    if scope not in ("L1", "L2", "L3"):
        scope = "L3"
    if market is not None and market not in VALID_QUERY_MARKETS:
        return SectorConstituentsResponse(
            level1_id=path.level1_id,
            level2_id=path.level2_id,
            level3_id=path.level3_id,
            scope=scope,
            market=market,
            items=[],
        )

    query_l1 = path.level1_id
    query_l2 = path.level2_id if scope in ("L2", "L3") else ""
    query_l3 = path.level3_id if scope == "L3" else ""

    constituents = []
    for market_candidate in _market_candidates(market):
        constituents = sector_precomputed_store.get_sector_constituents(
            level1_id=query_l1,
            level2_id=query_l2,
            level3_id=query_l3,
            market=market_candidate,
        )
        if constituents:
            break

    if not constituents:
        return SectorConstituentsResponse(
            level1_id=path.level1_id,
            level2_id=path.level2_id,
            level3_id=path.level3_id,
            scope=scope,
            market=market,
            items=[],
        )

    tickers = [c["ticker"] for c in constituents]
    historical = bool(str(start_date or "").strip() and str(end_date or "").strip())
    ticker_return_map = _ticker_return_map(
        sector_precomputed_store,
        tickers,
        days=days,
        start_date=start_date,
        end_date=end_date,
    )

    items: list[SectorConstituentItem] = []
    for c in constituents:
        ticker = c["ticker"]
        resolved_market = c["market"]
        stock = stock_store.get(resolved_market, ticker)
        if stock is None:
            continue
        quote = stock.stock_quote
        if quote is None:
            continue
        # Same ≥10亿 universe as Phase A / theme_state / movers (live quote).
        if not stock_passes_ticker_market_cap_min(stock):
            continue
        if not stock_is_equity_quote_type(stock):
            continue
        if stock_is_us_warrant_by_name(stock):
            continue

        window_change_percent = ticker_return_map.get(ticker, 0.0)
        change_percent = window_change_percent if historical else quote.change_percent

        items.append(
            SectorConstituentItem(
                ticker=stock.ticker,
                market=stock.market,
                name=_stock_bilingual_name(stock),
                currency=(stock.currency or CURRENCY_BY_MARKET.get(stock.market, "") or CURRENCY_BY_MARKET.get(resolved_market, "")).strip(),
                last_price=quote.last_price,
                change_percent=change_percent,
                window_change_percent=window_change_percent,
                turn_rate=quote.turn_rate,
                market_cap=quote.market_cap,
                pe=display_valuation_ratio(quote.pe),
                pb=display_valuation_ratio(quote.pb),
                amount=quote.amount,
            )
        )

    items.sort(key=lambda row: row.market_cap or 0.0, reverse=True)
    return SectorConstituentsResponse(
        level1_id=path.level1_id,
        level2_id=path.level2_id,
        level3_id=path.level3_id,
        scope=scope,
        market=market,
        items=items,
    )
