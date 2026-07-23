from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from dojo.client.async_client import AsyncDojo

from dojoagents.config.models import FinancialDashboardConfig
from dojoagents.harnesses.built_in.financial.services.financial_registry import FinancialDomainRegistry
from dojoagents.harnesses.built_in.financial.pipelines.precompute_sector_daily import (
    ProgressCallback,
    build_sector_precomputed,
)
from dojoagents.harnesses.built_in.financial.services.stock_quote_filter import apply_configured_ticker_market_cap_mins
from dojoagents.logging import LOGGER

_PHASE_LABELS: dict[str, str] = {
    "prepare": "Scan constituents",
    "compute": "Compute & stage",
    "publish": "Publish snapshot",
    "upload": "Upload dataset",
}


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


async def run_precompute_sector(args: argparse.Namespace) -> int:
    data_root_str = args.data_root or FinancialDashboardConfig.dashboard_data_root
    data_root = Path(data_root_str).expanduser().resolve()
    floors = apply_configured_ticker_market_cap_mins(getattr(args, "config", None))

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
            upload_client=client if args.upload else None,
            on_progress=on_progress,
        )
    finally:
        progress.close()

    if registry.sector_precomputed_store is not None:
        registry.sector_precomputed_store.reload(Path(manifest["published_dir"]))

    if getattr(args, "with_theme_state", False):
        from dojoagents.harnesses.built_in.financial.pipelines.precompute_theme_state_daily import build_theme_state_precomputed

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

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0
