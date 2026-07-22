from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from dojo.client.async_client import AsyncDojo

from dojoagents.config.models import FinancialDashboardConfig
from dojoagents.dashboard.services.financial_registry import FinancialDomainRegistry
from dojoagents.dashboard.services.precompute_sector_daily import PRECOMPUTE_DIR
from dojoagents.dashboard.services.precompute_theme_state_daily import (
    ProgressCallback,
    build_theme_state_precomputed,
)
from dojoagents.dashboard.services.stock_quote_filter import apply_configured_ticker_market_cap_mins
from dojoagents.logging import LOGGER

_PHASE_LABELS: dict[str, str] = {
    "load_phase_a": "Load Phase A",
    "volume": "Enrich volume",
    "fundamentals": "Fundamentals",
    "compute": "Compute theme-state",
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


async def run_precompute_sector_theme_state(args: argparse.Namespace) -> int:
    data_root_str = args.data_root or FinancialDashboardConfig.dashboard_data_root
    data_root = Path(data_root_str).expanduser().resolve()
    floors = apply_configured_ticker_market_cap_mins(getattr(args, "config", None))

    LOGGER.info(
        "Enriching unified sector precompute (theme + horizon + sector/ticker alpha) -> %s",
        data_root / PRECOMPUTE_DIR,
    )
    LOGGER.info("Ticker market-cap floors: %s", floors)

    progress = _PrecomputeProgressReporter()
    on_progress: ProgressCallback = progress.callback

    client = AsyncDojo()
    registry = FinancialDomainRegistry()
    # Phase B needs taxonomy + optional kline/benchmark/fin; sector A must already be published.
    await registry.init_and_load_all(client, data_root=data_root, preload=True)

    try:
        manifest = await build_theme_state_precomputed(
            data_root=data_root,
            sector_store=registry.sector_store,
            kline_store=None if args.skip_volume_enrich else registry.kline_store,
            benchmark_store=registry.benchmark_store,
            fin_store=None if args.skip_fundamentals else registry.stock_fin_indicators_store,
            start_date=args.start_date,
            end_date=args.end_date,
            upload_client=client if args.upload else None,
            skip_fundamentals=bool(args.skip_fundamentals),
            skip_volume_enrich=bool(args.skip_volume_enrich),
            on_progress=on_progress,
        )
    finally:
        progress.close()

    if registry.theme_state_precomputed_store is not None:
        registry.theme_state_precomputed_store.reload(Path(manifest["published_dir"]))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0
