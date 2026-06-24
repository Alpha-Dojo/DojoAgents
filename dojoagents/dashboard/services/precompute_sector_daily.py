"""Compute sector constituents and daily index levels from start_date onward."""

from __future__ import annotations

import hashlib
import json
import shutil
import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from dojoagents.dashboard.services.constituent_filter import ConstituentEligibilityChecker
from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.services.sector_store import ResolvedSectorPath, SectorStore
from dojoagents.dashboard.services.stock_sector_store import MARKETS, StockSectorStore
from dojoagents.dashboard.services.stock_store import StockStore

PRECOMPUTE_DIR = "dojo_sector_precomputed"
CONSTITUENTS_FILE = "constituents.parquet"
SECTOR_DAILY_FILE = "sector_daily.parquet"
TICKER_DAILY_FILE = "ticker_daily.parquet"
MANIFEST_FILE = "manifest.json"

DATA_START_DATE = "2025-01-01"
SCHEMA_VERSION = "3"

CONSTITUENT_COLUMNS = [
    "level1_id",
    "level2_id",
    "level3_id",
    "market",
    "ticker",
    "role",
    "market_cap",
    "pe",
]
TICKER_DAILY_COLUMNS = [
    "market",
    "ticker",
    "trade_date",
    "close",
    "daily_return_pct",
    "cumulative_return_pct",
]
SECTOR_DAILY_COLUMNS = [
    "trade_date",
    "scope",
    "market",
    "level1_id",
    "level2_id",
    "level3_id",
    "member_count",
    "member_count_with_return",
    "total_market_cap",
    "effective_weight_sum",
    "weighted_pe",
    "index_level",
    "daily_return_pct",
]


@dataclass(frozen=True)
class PrecomputeInputSnapshot:
    start_date: str
    end_date: str | None
    generated_at: str
    constituents: list[dict[str, Any]]
    ticker_daily_rows: list[dict[str, Any]]
    stats: dict[str, Any]


def _empty_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _previous_day(raw_date: str) -> str:
    return (date.fromisoformat(raw_date) - timedelta(days=1)).isoformat()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dedupe_kline_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["market"]), str(row["ticker"]), str(row["trade_date"]))
        deduped[key] = row
    return [deduped[key] for key in sorted(deduped)]


async def prepare_sector_precompute_input(
    *,
    sector_store: SectorStore,
    stock_sector_store: StockSectorStore,
    stock_store: StockStore,
    kline_store: KlineStore,
    start_date: str,
    end_date: str | None = None,
) -> PrecomputeInputSnapshot:
    lookback_start = _previous_day(start_date)
    checker = ConstituentEligibilityChecker(kline_store)
    generated_at = datetime.now(timezone.utc).isoformat()

    constituents: list[dict[str, Any]] = []
    ticker_daily_rows: list[dict[str, Any]] = []
    seen_constituents: set[tuple[str, str, str, str, str, str]] = set()
    seen_tickers: set[tuple[str, str]] = set()
    stats: dict[str, Any] = {
        "markets": {
            market: {
                "candidate_assignments": 0,
                "eligible_constituents": 0,
                "missing_stock": 0,
                "missing_quote": 0,
                "non_positive_cap": 0,
                "missing_kline": 0,
            }
            for market in MARKETS
        },
        "unresolved_assignments": len(stock_sector_store.unresolved_assignments(sector_store)),
    }

    for path in sector_store.iter_resolved_paths():
        for market in MARKETS:
            assignments = stock_sector_store.assignments_for_path(
                path,
                sector_store=sector_store,
                market=market,
                scope="L3",
            )
            stats["markets"][market]["candidate_assignments"] += len(assignments)
            for assignment in assignments:
                stock = stock_store.get(assignment.market, assignment.ticker)
                if stock is None:
                    stats["markets"][assignment.market]["missing_stock"] += 1
                    continue
                if stock.stock_quote is None:
                    stats["markets"][assignment.market]["missing_quote"] += 1
                    continue
                if stock.stock_quote.market_cap <= 0:
                    stats["markets"][assignment.market]["non_positive_cap"] += 1
                    continue
                if not await checker.is_eligible(stock):
                    stats["markets"][assignment.market]["missing_kline"] += 1
                    continue

                dedupe_key = (
                    assignment.market,
                    path.level1_id,
                    path.level2_id,
                    path.level3_id,
                    assignment.ticker,
                    assignment.role,
                )
                if dedupe_key in seen_constituents:
                    continue
                seen_constituents.add(dedupe_key)
                constituents.append(
                    {
                        "level1_id": path.level1_id,
                        "level2_id": path.level2_id,
                        "level3_id": path.level3_id,
                        "market": assignment.market,
                        "ticker": assignment.ticker,
                        "role": assignment.role,
                        "market_cap": float(stock.stock_quote.market_cap),
                        "pe": float(stock.stock_quote.pe) if stock.stock_quote.pe > 0 else None,
                    }
                )
                stats["markets"][assignment.market]["eligible_constituents"] += 1

                ticker_key = (assignment.market, assignment.ticker)
                if ticker_key in seen_tickers:
                    continue
                seen_tickers.add(ticker_key)
                response = await kline_store.get_or_fetch_kline(
                    assignment.ticker,
                    market=assignment.market,
                    kline_t="1D",
                    start_time=lookback_start,
                    end_time=end_date,
                    limit=0,
                )
                if response is None or not response.bars:
                    continue
                for bar in response.bars:
                    ticker_daily_rows.append(
                        {
                            "market": assignment.market,
                            "ticker": assignment.ticker,
                            "trade_date": str(bar.bar_time)[:10],
                            "close": float(bar.close),
                        }
                    )

    return PrecomputeInputSnapshot(
        start_date=start_date,
        end_date=end_date,
        generated_at=generated_at,
        constituents=constituents,
        ticker_daily_rows=_dedupe_kline_rows(ticker_daily_rows),
        stats=stats,
    )


def _compute_ticker_daily(snapshot: PrecomputeInputSnapshot) -> pd.DataFrame:
    frame = pd.DataFrame(snapshot.ticker_daily_rows)
    if frame.empty:
        raise ValueError("No kline data available for sector precompute constituents.")

    frame = frame.sort_values(["market", "ticker", "trade_date"])
    frame["trade_date"] = frame["trade_date"].astype(str)
    frame["daily_return_pct"] = frame.groupby(["market", "ticker"])["close"].pct_change() * 100.0
    first_close = frame.groupby(["market", "ticker"])["close"].transform("first")
    frame["cumulative_return_pct"] = ((frame["close"] / first_close - 1.0) * 100.0).where(first_close > 0)
    frame = frame[frame["trade_date"] >= snapshot.start_date].copy()
    frame["daily_return_pct"] = frame["daily_return_pct"].round(4)
    frame["cumulative_return_pct"] = frame["cumulative_return_pct"].round(4)
    return frame[TICKER_DAILY_COLUMNS]


def _weighted_pe(constituents: pd.DataFrame) -> float | None:
    valid = constituents[(constituents["market_cap"] > 0) & (constituents["pe"].notna()) & (constituents["pe"] > 0)]
    if valid.empty:
        return None
    cap_sum = float(valid["market_cap"].sum())
    earnings = float((valid["market_cap"] / valid["pe"]).sum())
    if cap_sum <= 0 or earnings <= 0:
        return None
    return round(cap_sum / earnings, 4)


def _build_index_rows(
    *,
    scope: str,
    market: str,
    path: ResolvedSectorPath,
    members: pd.DataFrame,
    returns_pivot: pd.DataFrame,
) -> list[dict[str, Any]]:
    members = members.sort_values(["market", "ticker", "role"]).drop_duplicates(subset=["market", "ticker"], keep="first").copy()
    tickers = [(str(row["market"]), str(row["ticker"])) for _, row in members.iterrows()]
    valid_columns = [column for column in tickers if column in returns_pivot.columns]
    if not valid_columns:
        return []

    member_count = int(len({ticker for _, ticker in valid_columns}))
    total_market_cap = float(members["market_cap"].sum())
    pe_value = _weighted_pe(members)
    weights = {(str(row["market"]), str(row["ticker"])): float(row["market_cap"]) for _, row in members.iterrows()}

    rows: list[dict[str, Any]] = []
    index_level = 100.0
    for trade_date in returns_pivot.index:
        available = []
        for column in valid_columns:
            value = returns_pivot.at[trade_date, column]
            if pd.isna(value):
                continue
            weight = weights.get(column, 0.0)
            if weight <= 0:
                continue
            available.append((float(value), weight))
        if not available:
            continue
        effective_weight_sum = float(sum(weight for _, weight in available))
        daily_return_pct = sum(value * weight for value, weight in available) / effective_weight_sum
        index_level *= 1 + daily_return_pct / 100.0
        rows.append(
            {
                "trade_date": str(trade_date),
                "scope": scope,
                "market": market,
                "level1_id": path.level1_id,
                "level2_id": path.level2_id if scope in {"L2", "L3"} else "",
                "level3_id": path.level3_id if scope == "L3" else "",
                "member_count": member_count,
                "member_count_with_return": len(available),
                "total_market_cap": round(total_market_cap, 4),
                "effective_weight_sum": round(effective_weight_sum, 4),
                "weighted_pe": pe_value,
                "index_level": round(index_level, 4),
                "daily_return_pct": round(daily_return_pct, 4),
            }
        )
    return rows


def compute_sector_precomputed_frames(snapshot: PrecomputeInputSnapshot) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    constituents_df = pd.DataFrame(snapshot.constituents)
    if constituents_df.empty:
        raise ValueError("No eligible constituents available for sector precompute.")
    constituents_df = constituents_df[CONSTITUENT_COLUMNS]

    ticker_daily_df = _compute_ticker_daily(snapshot)
    returns_pivot = ticker_daily_df.pivot_table(
        index="trade_date",
        columns=["market", "ticker"],
        values="daily_return_pct",
        aggfunc="last",
    ).sort_index()

    sector_daily_rows: list[dict[str, Any]] = []
    l3_groups = constituents_df.groupby(["market", "level1_id", "level2_id", "level3_id"], sort=True)
    for (market, level1_id, level2_id, level3_id), members in l3_groups:
        path = ResolvedSectorPath(
            level1_id=level1_id,
            level2_id=level2_id,
            level3_id=level3_id,
            level1_zh="",
            level1_en="",
            level2_zh="",
            level2_en="",
            level3_zh="",
            level3_en="",
        )
        sector_daily_rows.extend(
            _build_index_rows(
                scope="L3",
                market=market,
                path=path,
                members=members,
                returns_pivot=returns_pivot,
            )
        )

    l2_groups = constituents_df.groupby(["market", "level1_id", "level2_id"], sort=True)
    for (market, level1_id, level2_id), members in l2_groups:
        path = ResolvedSectorPath(
            level1_id=level1_id,
            level2_id=level2_id,
            level3_id="",
            level1_zh="",
            level1_en="",
            level2_zh="",
            level2_en="",
            level3_zh="",
            level3_en="",
        )
        sector_daily_rows.extend(
            _build_index_rows(
                scope="L2",
                market=market,
                path=path,
                members=members,
                returns_pivot=returns_pivot,
            )
        )

    l1_groups = constituents_df.groupby(["market", "level1_id"], sort=True)
    for (market, level1_id), members in l1_groups:
        path = ResolvedSectorPath(
            level1_id=level1_id,
            level2_id="",
            level3_id="",
            level1_zh="",
            level1_en="",
            level2_zh="",
            level2_en="",
            level3_zh="",
            level3_en="",
        )
        sector_daily_rows.extend(
            _build_index_rows(
                scope="L1",
                market=market,
                path=path,
                members=members,
                returns_pivot=returns_pivot,
            )
        )

    sector_daily_df = pd.DataFrame(sector_daily_rows)
    if sector_daily_df.empty:
        raise ValueError("Sector daily output is empty; refusing to publish an empty snapshot.")
    sector_daily_df = sector_daily_df[SECTOR_DAILY_COLUMNS]

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "build_id": snapshot.generated_at.replace(":", "").replace("-", ""),
        "generated_at": snapshot.generated_at,
        "window_start": snapshot.start_date,
        "window_end": snapshot.end_date or str(sector_daily_df["trade_date"].max()),
        "weighting_method": "latest_market_cap_snapshot",
        "constituent_count": int(len(constituents_df)),
        "ticker_daily_rows": int(len(ticker_daily_df)),
        "sector_daily_rows": int(len(sector_daily_df)),
        "latest_trade_date_by_market": {market: str(group["trade_date"].max()) for market, group in sector_daily_df.groupby("market")},
        "stats": snapshot.stats,
    }
    return constituents_df, ticker_daily_df, sector_daily_df, manifest


def validate_precomputed_frames(
    constituents_df: pd.DataFrame,
    ticker_daily_df: pd.DataFrame,
    sector_daily_df: pd.DataFrame,
) -> None:
    if list(constituents_df.columns) != CONSTITUENT_COLUMNS:
        raise ValueError("Constituent schema mismatch.")
    if list(ticker_daily_df.columns) != TICKER_DAILY_COLUMNS:
        raise ValueError("Ticker daily schema mismatch.")
    if list(sector_daily_df.columns) != SECTOR_DAILY_COLUMNS:
        raise ValueError("Sector daily schema mismatch.")
    if not bool(constituents_df["role"].isin(["primary", "secondary"]).all()):
        raise ValueError("Constituent role contains unsupported values.")
    if ticker_daily_df.duplicated(subset=["market", "ticker", "trade_date"]).any():
        raise ValueError("Ticker daily contains duplicate market/ticker/date rows.")
    if sector_daily_df.duplicated(subset=["market", "scope", "level1_id", "level2_id", "level3_id", "trade_date"]).any():
        raise ValueError("Sector daily contains duplicate scope/path/date rows.")


def compute_and_stage_sector_precomputed(
    snapshot: PrecomputeInputSnapshot,
    out_dir: Path,
) -> tuple[dict[str, Any], Path]:
    constituents_df, ticker_daily_df, sector_daily_df, manifest = compute_sector_precomputed_frames(snapshot)
    validate_precomputed_frames(constituents_df, ticker_daily_df, sector_daily_df)

    staging_dir = out_dir.with_name(f"{out_dir.name}.staging")
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    constituents_path = staging_dir / CONSTITUENTS_FILE
    ticker_daily_path = staging_dir / TICKER_DAILY_FILE
    sector_daily_path = staging_dir / SECTOR_DAILY_FILE
    constituents_df.to_parquet(constituents_path, index=False)
    ticker_daily_df.to_parquet(ticker_daily_path, index=False)
    sector_daily_df.to_parquet(sector_daily_path, index=False)

    manifest["files"] = {
        CONSTITUENTS_FILE: {"rows": len(constituents_df), "sha256": _file_sha256(constituents_path)},
        TICKER_DAILY_FILE: {"rows": len(ticker_daily_df), "sha256": _file_sha256(ticker_daily_path)},
        SECTOR_DAILY_FILE: {"rows": len(sector_daily_df), "sha256": _file_sha256(sector_daily_path)},
    }
    (staging_dir / MANIFEST_FILE).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest, staging_dir


def publish_staged_sector_precomputed(staging_dir: Path, out_dir: Path) -> Path:
    backup_dir = out_dir.with_name(f"{out_dir.name}.bak")
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    if out_dir.exists():
        out_dir.replace(backup_dir)
    staging_dir.replace(out_dir)
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    return out_dir


async def build_sector_precomputed(
    data_root: Path,
    sector_store: SectorStore,
    stock_sector_store: StockSectorStore,
    stock_store: StockStore,
    kline_store: KlineStore,
    *,
    start_date: str = DATA_START_DATE,
    end_date: str | None = None,
    out_dir: Path | None = None,
    upload_client: Any | None = None,
    upload_dataset_name: str = PRECOMPUTE_DIR,
) -> dict[str, Any]:
    """Compute sector constituents and daily index levels from ``start_date`` onward."""
    data_root = data_root.expanduser().resolve()
    out_dir = (out_dir or (data_root / PRECOMPUTE_DIR)).resolve()

    snapshot = await prepare_sector_precompute_input(
        sector_store=sector_store,
        stock_sector_store=stock_sector_store,
        stock_store=stock_store,
        kline_store=kline_store,
        start_date=start_date,
        end_date=end_date,
    )
    manifest, staging_dir = await asyncio.to_thread(
        compute_and_stage_sector_precomputed,
        snapshot,
        out_dir,
    )
    published_dir = await asyncio.to_thread(
        publish_staged_sector_precomputed,
        staging_dir,
        out_dir,
    )
    manifest["published_dir"] = str(published_dir)
    if upload_client is not None:
        await upload_client.upload_dataset(upload_dataset_name, str(published_dir))
        manifest["uploaded_dataset"] = upload_dataset_name
    return manifest
