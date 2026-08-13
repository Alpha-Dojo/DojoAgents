from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
from dojo import ConflictError
from dojo.client.async_client import AsyncDojo

from dojoagents.config.models import FinancialDashboardConfig
from dojoagents.dashboard.services.financial_registry import FinancialDomainRegistry
from dojoagents.dashboard.jobs.precompute.sector_daily import (
    ProgressCallback,
    build_sector_precomputed,
)
from dojoagents.dashboard.services.stock_quote_filter import apply_configured_ticker_market_cap_mins
from dojoagents.logging import LOGGER

_PHASE_LABELS: dict[str, str] = {
    "prepare": "Scan constituents",
    "kline": "Load constituent K-lines",
    "compute": "Compute & stage",
    "publish": "Publish snapshot",
    "upload": "Upload dataset",
    "upload_api": "Upload qdata API",
}
_API_BATCH_SIZE = 10000


def configure_parser(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "precompute-sector",
        help="Precompute Dashboard sector daily metrics and returns",
    )
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--start-date", default="2025-01-01")
    parser.add_argument("--market", choices=("us", "cn", "hk"), default=None)
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--upload-api", action="store_true", help="Write the selected market through DojoSDK qdata POST endpoints")
    parser.add_argument("--with-theme-state", action="store_true")
    parser.add_argument("--skip-fundamentals", action="store_true")
    parser.add_argument("--skip-volume-enrich", action="store_true")


class _PrecomputeProgressReporter:
    def __init__(self) -> None:
        try:
            from tqdm import tqdm
        except ImportError:
            self._tqdm: Any | None = None
        else:
            self._tqdm = tqdm
        self._bars: dict[str, Any] = {}

    def callback(self, phase: str, current: int, total: int) -> None:
        if self._tqdm is None:
            return

        label = _PHASE_LABELS.get(phase, phase)
        bar = self._bars.get(phase)
        if bar is None:
            bar = self._tqdm(total=max(total, 1), desc=label, position=len(self._bars), leave=True)
            self._bars[phase] = bar
        elif bar.total != total:
            bar.total = max(total, 1)
        bar.n = min(current, bar.total)
        bar.refresh()
        if current >= bar.total:
            bar.close()

    def close(self) -> None:
        for bar in self._bars.values():
            if not bar.disable:
                bar.close()
        self._bars.clear()


def _source_market(market: str) -> str:
    return "sh" if market == "cn" else market


def _market_records(path: Path, market: str, *, id_columns: tuple[str, ...] = (), start_date: str | None = None) -> list[dict[str, Any]]:
    frame = pd.read_parquet(path)
    frame = frame[frame["market"].astype(str).str.lower() == _source_market(market)].copy()
    if start_date and "trade_date" in frame:
        frame = frame[frame["trade_date"].astype(str) >= start_date]
    frame["market"] = market
    for column in id_columns:
        original = frame[column]
        numeric = pd.to_numeric(original, errors="coerce")
        invalid = original.notna() & original.astype(str).str.strip().ne("") & numeric.isna()
        if invalid.any():
            raise ValueError(f"{path.name}.{column} contains a non-numeric sector id")
        frame[column] = numeric.fillna(0).astype("int64")
    return json.loads(frame.to_json(orient="records", date_format="iso"))


async def _write_api_batches(client: AsyncDojo, method_name: str, rows: list[dict[str, Any]]) -> None:
    method = getattr(client.sectors, method_name)
    for offset in range(0, len(rows), _API_BATCH_SIZE):
        batch = rows[offset : offset + _API_BATCH_SIZE]
        try:
            await method(observations=batch)
        except ConflictError:
            await method(observations=batch, replace=True)
        LOGGER.info("Wrote %s qdata rows: %d/%d", method_name, min(offset + len(batch), len(rows)), len(rows))


async def upload_market_precomputed(client: AsyncDojo, published_dir: Path, market: str, *, start_date: str | None = None) -> dict[str, int]:
    datasets = (
        ("create_constituents", "constituents.parquet", ("level1_id", "level2_id", "level3_id"), None),
        ("create_ticker_daily", "ticker_daily.parquet", (), start_date),
        ("create_daily", "sector_daily.parquet", ("level1_id", "level2_id", "level3_id"), start_date),
    )
    counts: dict[str, int] = {}
    for method_name, filename, id_columns, dataset_start_date in datasets:
        rows = _market_records(published_dir / filename, market, id_columns=id_columns, start_date=dataset_start_date)
        if rows:
            await _write_api_batches(client, method_name, rows)
        counts[filename] = len(rows)
    return counts


async def run_precompute_sector(args: argparse.Namespace) -> int:
    data_root_str = args.data_root or FinancialDashboardConfig.dashboard_data_root
    data_root = Path(data_root_str).expanduser().resolve()
    floors = apply_configured_ticker_market_cap_mins(getattr(args, "config", None))
    if args.upload_api and not args.market:
        raise ValueError("--market is required with --upload-api")

    LOGGER.info(f"Precomputing sector data -> {data_root / 'dojo_sector_precomputed'}")
    LOGGER.info(f"Window start: {args.start_date}")
    LOGGER.info("Ticker market-cap floors: %s", floors)

    progress = _PrecomputeProgressReporter()
    on_progress: ProgressCallback = progress.callback

    client = AsyncDojo()
    registry = FinancialDomainRegistry()
    await registry.init_and_load_all(client, data_root=data_root, preload=True)

    try:
        manifest = await build_sector_precomputed(
            data_root=data_root,
            sector_store=registry.sector_store,
            stock_sector_store=registry.stock_sector_store,
            stock_store=registry.stock_store,
            kline_store=registry.kline_store,
            start_date=args.start_date,
            market=_source_market(args.market) if args.market else None,
            upload_client=client if args.upload else None,
            on_progress=on_progress,
        )
    finally:
        progress.close()

    if registry.sector_precomputed_store is not None:
        registry.sector_precomputed_store.reload(Path(manifest["published_dir"]))

    if args.upload_api:
        counts = await upload_market_precomputed(client, Path(manifest["published_dir"]), args.market, start_date=args.start_date)
        manifest["uploaded_api"] = {"market": args.market, "rows": counts}

    if getattr(args, "with_theme_state", False):
        from dojoagents.dashboard.jobs.precompute.theme_state_daily import build_theme_state_precomputed

        LOGGER.info("Phase A complete; enriching dojo_sector_precomputed with theme-state + horizon")
        theme_progress = _PrecomputeProgressReporter()
        try:
            theme_manifest = await build_theme_state_precomputed(
                data_root=data_root,
                sector_store=registry.sector_store,
                kline_store=None if getattr(args, "skip_volume_enrich", False) else registry.kline_store,
                benchmark_store=registry.benchmark_store,
                fin_store=(None if getattr(args, "skip_fundamentals", False) else registry.stock_fin_indicators_store),
                start_date=args.start_date,
                upload_client=client if args.upload else None,
                skip_fundamentals=bool(getattr(args, "skip_fundamentals", False)),
                skip_volume_enrich=bool(getattr(args, "skip_volume_enrich", False)),
                on_progress=theme_progress.callback,
            )
        finally:
            theme_progress.close()
        if registry.sector_precomputed_store is not None:
            registry.sector_precomputed_store.reload(Path(theme_manifest["published_dir"]))
        if registry.theme_state_precomputed_store is not None:
            registry.theme_state_precomputed_store.reload(Path(theme_manifest["published_dir"]))
        manifest = theme_manifest

    LOGGER.info("%s", json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0
