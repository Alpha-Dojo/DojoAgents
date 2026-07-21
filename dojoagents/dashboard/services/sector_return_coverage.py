"""Coverage gates for market-cap-weighted sector daily returns.

Same-market tickers should share one as-of session. Sparse trailing bars
(e.g. one micro-cap ahead of the rest) are treated as missing data, not as a
valid sector print.
"""

from __future__ import annotations

from typing import Mapping

import pandas as pd

# Sector day is usable only when enough names *and* enough cap are present.
MIN_SECTOR_RETURN_MEMBER_COVERAGE = 0.50
MIN_SECTOR_RETURN_CAP_COVERAGE = 0.80

# Market as-of is the latest date covering at least this share of tickers.
MIN_MARKET_AS_OF_TICKER_COVERAGE = 0.50


def sector_day_return_coverage_ok(
    *,
    member_count: int,
    member_count_with_return: int,
    total_market_cap: float,
    effective_weight_sum: float,
    min_member_coverage: float = MIN_SECTOR_RETURN_MEMBER_COVERAGE,
    min_cap_coverage: float = MIN_SECTOR_RETURN_CAP_COVERAGE,
) -> bool:
    """True when a sector daily return may be published / ranked."""
    members = int(member_count or 0)
    with_return = int(member_count_with_return or 0)
    if members <= 0 or with_return <= 0:
        return False
    if with_return / members < min_member_coverage:
        return False

    total_cap = float(total_market_cap or 0.0)
    effective_cap = float(effective_weight_sum or 0.0)
    if total_cap <= 0 or effective_cap <= 0:
        return False
    if effective_cap / total_cap < min_cap_coverage:
        return False
    return True


def filter_usable_sector_daily_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Drop sector_daily rows that fail count/cap coverage gates."""
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()

    required = {
        "member_count",
        "member_count_with_return",
        "total_market_cap",
        "effective_weight_sum",
    }
    if not required.issubset(df.columns):
        return df

    member_count = pd.to_numeric(df["member_count"], errors="coerce").fillna(0.0)
    with_return = pd.to_numeric(df["member_count_with_return"], errors="coerce").fillna(0.0)
    total_cap = pd.to_numeric(df["total_market_cap"], errors="coerce").fillna(0.0)
    effective_cap = pd.to_numeric(df["effective_weight_sum"], errors="coerce").fillna(0.0)

    member_ok = (member_count > 0) & ((with_return / member_count) >= MIN_SECTOR_RETURN_MEMBER_COVERAGE)
    cap_ok = (total_cap > 0) & ((effective_cap / total_cap) >= MIN_SECTOR_RETURN_CAP_COVERAGE)
    return df.loc[member_ok & cap_ok].copy()


def resolve_market_as_of_by_market(
    ticker_daily: pd.DataFrame,
    *,
    min_ticker_coverage: float = MIN_MARKET_AS_OF_TICKER_COVERAGE,
) -> dict[str, str]:
    """Latest trade date per market with sufficient ticker coverage.

    Ignores trailing dates that only a thin minority of names have printed
    (typical data-gap / partial-ingest artifact).
    """
    if ticker_daily is None or ticker_daily.empty:
        return {}
    if "market" not in ticker_daily.columns or "trade_date" not in ticker_daily.columns:
        return {}
    if "ticker" not in ticker_daily.columns:
        return {}

    frame = ticker_daily[["market", "ticker", "trade_date"]].copy()
    frame["market"] = frame["market"].astype(str)
    frame["ticker"] = frame["ticker"].astype(str)
    frame["trade_date"] = frame["trade_date"].astype(str)

    as_of: dict[str, str] = {}
    for market, group in frame.groupby("market", sort=False):
        total_tickers = int(group["ticker"].nunique())
        if total_tickers <= 0:
            continue
        by_date = group.groupby("trade_date", sort=False)["ticker"].nunique()
        eligible = by_date[by_date / total_tickers >= min_ticker_coverage]
        if eligible.empty:
            as_of[str(market)] = str(by_date.idxmax())
        else:
            as_of[str(market)] = str(max(eligible.index))
    return as_of


def clip_frame_to_market_as_of(
    df: pd.DataFrame,
    as_of_by_market: Mapping[str, str],
    *,
    market_col: str = "market",
    date_col: str = "trade_date",
) -> pd.DataFrame:
    """Keep rows on or before each market's as-of date."""
    if df is None or df.empty or not as_of_by_market:
        return df if df is not None else pd.DataFrame()
    if market_col not in df.columns or date_col not in df.columns:
        return df

    markets = df[market_col].astype(str)
    dates = df[date_col].astype(str)
    keep = pd.Series(False, index=df.index)
    for market, as_of in as_of_by_market.items():
        if not as_of:
            continue
        keep |= (markets == str(market)) & (dates <= str(as_of))
    # Markets without a resolved as-of stay untouched.
    known = markets.isin({str(m) for m in as_of_by_market})
    keep |= ~known
    return df.loc[keep].copy()


def restrict_frame_to_market_as_of_exact(
    df: pd.DataFrame,
    as_of_by_market: Mapping[str, str],
    *,
    market_col: str = "market",
    date_col: str = "trade_date",
) -> pd.DataFrame:
    """Keep only rows that land exactly on each market's as-of date."""
    if df is None or df.empty or not as_of_by_market:
        return df if df is not None else pd.DataFrame()
    if market_col not in df.columns or date_col not in df.columns:
        return df

    markets = df[market_col].astype(str)
    dates = df[date_col].astype(str)
    keep = pd.Series(False, index=df.index)
    for market, as_of in as_of_by_market.items():
        if not as_of:
            continue
        keep |= (markets == str(market)) & (dates == str(as_of))
    return df.loc[keep].copy()
