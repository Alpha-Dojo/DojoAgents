"""Compute sector constituents and daily index levels from start_date onward."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from dojoagents.dashboard.services.constituent_filter import is_sector_constituent_eligible
from dojoagents.dashboard.services.stock_sector_store import MARKETS, StockSectorStore
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.services.kline_store import KlineStore

PRECOMPUTE_DIR = "dojo_sector_precomputed"
CONSTITUENTS_FILE = "constituents.parquet"
SECTOR_DAILY_FILE = "sector_daily.parquet"
TICKER_DAILY_FILE = "ticker_daily.parquet"
MANIFEST_FILE = "manifest.json"

DATA_START_DATE = "2025-01-01"


def _build_index_rows(
    *,
    scope: str,
    level1_id: str,
    level2_id: str,
    level3_id: str,
    market: str,
    tickers: list[str],
    returns_pivot: pd.DataFrame,
    cap_weight: dict[str, float],
    stock_store: StockStore,
) -> list[dict]:
    valid_tickers = [t for t in tickers if t in returns_pivot.columns]
    if not valid_tickers:
        return []

    weights = {t: cap_weight.get(t, 0) for t in valid_tickers}
    total_w = sum(weights.values())
    if total_w <= 0:
        return []

    member_count = len(valid_tickers)
    total_cap = sum(weights.values())
    pe_caps = []
    for ticker in valid_tickers:
        stock = stock_store.get(market, ticker)
        if stock and stock.quote and stock.quote.pe > 0:
            pe_caps.append((stock.quote.market_cap, stock.quote.pe))
    weighted_pe = None
    if pe_caps:
        cap_sum = sum(c for c, _ in pe_caps)
        earn = sum(c / p for c, p in pe_caps)
        if earn > 0:
            weighted_pe = cap_sum / earn

    rows: list[dict] = []
    index_level = 100.0
    for trade_date in returns_pivot.index:
        if str(trade_date) < DATA_START_DATE:
            continue
        day_returns = []
        day_weights = []
        for ticker in valid_tickers:
            val = returns_pivot.at[trade_date, ticker]
            if pd.isna(val):
                continue
            day_returns.append(float(val))
            day_weights.append(weights[ticker])
        if not day_returns:
            continue
        w_sum = sum(day_weights)
        daily_ret = sum(r * w for r, w in zip(day_returns, day_weights)) / w_sum
        index_level *= 1 + daily_ret / 100
        rows.append(
            {
                "trade_date": str(trade_date),
                "scope": scope,
                "market": market,
                "level1_id": level1_id,
                "level2_id": level2_id,
                "level3_id": level3_id,
                "member_count": member_count,
                "total_market_cap": total_cap,
                "weighted_pe": weighted_pe,
                "index_level": round(index_level, 4),
                "daily_return_pct": round(daily_ret, 4),
            }
        )
    return rows


def build_sector_precomputed(
    data_root: Path,
    sector_store: StockSectorStore,
    stock_store: StockStore,
    kline_store: KlineStore,
    *,
    start_date: str = DATA_START_DATE,
    out_dir: Path | None = None,
) -> dict:
    """Compute sector constituents and daily index levels from ``start_date`` onward."""
    data_root = data_root.resolve()

    if out_dir is None:
        out_dir = data_root / PRECOMPUTE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    constituent_rows: list[dict] = []
    l3_groups: dict[tuple[str, str, str, str], list[str]] = {}
    l2_groups: dict[tuple[str, str, str], set[str]] = {}
    l1_groups: dict[tuple[str, str], set[str]] = {}
    cap_weight: dict[str, float] = {}
    seen_constituents: set[tuple[str, str, str, str, str]] = set()

    for path in sector_store.iter_resolved_paths():
        for market in MARKETS:
            tickers: list[str] = []
            for assignment in sector_store.assignments_for_path(path, market=market, scope="L3"):
                stock = stock_store.get(assignment.market, assignment.ticker)
                if not is_sector_constituent_eligible(stock, kline_store):
                    continue
                dedupe = (path.level1_id, path.level2_id, path.level3_id, market, assignment.ticker)
                if dedupe in seen_constituents:
                    continue
                seen_constituents.add(dedupe)
                tickers.append(assignment.ticker)
                cap_weight[assignment.ticker] = max(
                    cap_weight.get(assignment.ticker, 0),
                    float(stock.quote.market_cap),
                )
                constituent_rows.append(
                    {
                        "level1_id": path.level1_id,
                        "level2_id": path.level2_id,
                        "level3_id": path.level3_id,
                        "market": market,
                        "ticker": assignment.ticker,
                        "role": assignment.role,
                        "market_cap": stock.quote.market_cap,
                        "weighted_pe": stock.quote.pe if stock.quote.pe > 0 else None,
                    }
                )
            if not tickers:
                continue
            l3_key = (path.level1_id, path.level2_id, path.level3_id, market)
            l3_groups[l3_key] = tickers
            l2_key = (path.level1_id, path.level2_id, market)
            l2_groups.setdefault(l2_key, set()).update(tickers)
            l1_key = (path.level1_id, market)
            l1_groups.setdefault(l1_key, set()).update(tickers)

    constituents_df = pd.DataFrame(constituent_rows)
    constituents_df.to_parquet(out_dir / CONSTITUENTS_FILE, index=False)

    constituent_tickers = sorted({t for tickers in l3_groups.values() for t in tickers})
    # Load klines. We will load parquet directly for speed.
    kline_path = data_root / "datasets" / "dojo_stock_kline" / "data.parquet"

    kline_df = pd.read_parquet(kline_path, filters=[("symbol", "in", constituent_tickers)])
    kline_df = kline_df[kline_df["kline_t"] == "1D"].copy()
    kline_df["trade_date"] = pd.to_datetime(kline_df["bar_time"]).dt.strftime("%Y-%m-%d")
    kline_df = kline_df[kline_df["trade_date"] >= start_date]
    kline_df = kline_df.sort_values(["symbol", "trade_date"])
    kline_df["daily_return_pct"] = kline_df.groupby("symbol")["close"].pct_change() * 100
    first_close = kline_df.groupby("symbol")["close"].transform("first")
    kline_df["cumulative_return_pct"] = ((kline_df["close"] / first_close - 1) * 100).where(first_close > 0)
    kline_df["cumulative_return_pct"] = kline_df["cumulative_return_pct"].round(4)

    ticker_daily_df = kline_df[["symbol", "trade_date", "close", "daily_return_pct", "cumulative_return_pct"]].rename(columns={"symbol": "ticker"})
    ticker_daily_df.to_parquet(out_dir / TICKER_DAILY_FILE, index=False)

    returns_pivot = ticker_daily_df.pivot(index="trade_date", columns="ticker", values="daily_return_pct")
    returns_pivot = returns_pivot.sort_index()

    sector_daily_rows: list[dict] = []
    for level1_id, level2_id, level3_id, market in l3_groups:
        sector_daily_rows.extend(
            _build_index_rows(
                scope="L3",
                level1_id=level1_id,
                level2_id=level2_id,
                level3_id=level3_id,
                market=market,
                tickers=l3_groups[(level1_id, level2_id, level3_id, market)],
                returns_pivot=returns_pivot,
                cap_weight=cap_weight,
                stock_store=stock_store,
            )
        )

    for level1_id, level2_id, market in l2_groups:
        sector_daily_rows.extend(
            _build_index_rows(
                scope="L2",
                level1_id=level1_id,
                level2_id=level2_id,
                level3_id="",
                market=market,
                tickers=sorted(l2_groups[(level1_id, level2_id, market)]),
                returns_pivot=returns_pivot,
                cap_weight=cap_weight,
                stock_store=stock_store,
            )
        )

    for level1_id, market in l1_groups:
        sector_daily_rows.extend(
            _build_index_rows(
                scope="L1",
                level1_id=level1_id,
                level2_id="",
                level3_id="",
                market=market,
                tickers=sorted(l1_groups[(level1_id, market)]),
                returns_pivot=returns_pivot,
                cap_weight=cap_weight,
                stock_store=stock_store,
            )
        )

    sector_daily_df = pd.DataFrame(sector_daily_rows)
    sector_daily_df.to_parquet(out_dir / SECTOR_DAILY_FILE, index=False)

    latest_by_market = {m: sector_daily_df[sector_daily_df["market"] == m]["trade_date"].max() for m in MARKETS if not sector_daily_df[sector_daily_df["market"] == m].empty}

    manifest = {
        "version": "2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_start": start_date,
        "constituent_count": len(constituents_df),
        "sector_daily_rows": len(sector_daily_df),
        "ticker_daily_rows": len(ticker_daily_df),
        "latest_trade_date_by_market": latest_by_market,
    }
    (out_dir / MANIFEST_FILE).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return manifest
