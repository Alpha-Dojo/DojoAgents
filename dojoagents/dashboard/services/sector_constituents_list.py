from __future__ import annotations

import math
from typing import Any

from dojoagents.dashboard.services.market_sector_lead import _stock_bilingual_name
from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.services.sector_constituents import MARKETS, SectorLevel
from dojoagents.dashboard.services.sector_store import ResolvedSectorPath
from dojoagents.dashboard.services.stock_sector_store import StockSectorStore
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.schemas.dojo_sphere import SectorConstituentItem, SectorConstituentsResponse

CURRENCY_BY_MARKET = {"us": "USD", "sh": "CNY", "hk": "HKD"}


def _display_ratio(value: float | None) -> float | None:
    """Keep negative PE/PB for display; omit only missing, non-finite, or zero."""
    if value is None or not math.isfinite(value) or value == 0:
        return None
    return float(value)


async def list_sector_constituents(
    stock_store: StockStore,
    stock_sector_store: StockSectorStore,
    kline_store: KlineStore,
    sector_precomputed_store: Any,
    path: ResolvedSectorPath,
    *,
    scope: SectorLevel = "L3",
    market: str | None = None,
    days: int | None = None,
    window_start: str | None = None,
) -> SectorConstituentsResponse:
    """Constituents for L1/L2/L3 scope of the selected sector path."""
    if scope not in ("L1", "L2", "L3"):
        scope = "L3"
    if market is not None and market not in MARKETS:
        return SectorConstituentsResponse(
            level1_id=path.level1_id,
            level2_id=path.level2_id,
            level3_id=path.level3_id,
            scope=scope,
            market=market,
            items=[],
        )

    constituents = sector_precomputed_store.get_sector_constituents(
        level1_id=path.level1_id,
        level2_id=path.level2_id,
        level3_id=path.level3_id,
        market=market,
    )

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

    if days and days > 0:
        ticker_returns = sector_precomputed_store.get_ticker_daily_by_window(days, tickers)
    else:
        # TODO handle window_start if needed, or fallback to default
        ticker_returns = sector_precomputed_store.get_ticker_daily_by_window(365, tickers)

    ticker_return_map = {tr["ticker"]: tr["daily_return_pct"] for tr in ticker_returns}

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

        window_change_percent = ticker_return_map.get(ticker, 0.0)

        items.append(
            SectorConstituentItem(
                ticker=stock.ticker,
                market=stock.market,
                name=_stock_bilingual_name(stock),
                currency=(stock.currency or CURRENCY_BY_MARKET.get(stock.market, "")).strip(),
                last_price=quote.last_price,
                change_percent=quote.change_percent,
                window_change_percent=window_change_percent,
                turn_rate=quote.turn_rate,
                market_cap=quote.market_cap,
                pe=_display_ratio(quote.pe),
                pb=_display_ratio(quote.pb),
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
