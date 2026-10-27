from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from dojoagents.config.loader import ConfigStore
from dojoagents.config.models import FinancialDashboardConfig
from dojoagents.dojo_sdk import close_async_dojo, create_async_dojo
from dojoagents.dashboard.services.financial_registry import FinancialDomainRegistry
from dojoagents.dashboard.jobs.precompute.sector_daily import PRECOMPUTE_DIR
from dojoagents.dashboard.jobs.precompute.theme_state_daily import (
    ProgressCallback,
    build_theme_state_precomputed,
)
from dojoagents.dashboard.services.stock_quote_filter import apply_configured_ticker_market_cap_mins
from dojoagents.dashboard.cli.precompute_sector import log_precompute_startup, log_precompute_sdk_runtime
from dojoagents.logging import LOGGER

_PHASE_LABELS: dict[str, str] = {
    "load_phase_a": "Load Phase A",
    "volume": "Enrich volume",
    "fundamentals": "Fundamentals",
    "compute": "Compute theme-state",
    "publish": "Publish snapshot",
    "upload": "Upload dataset",
}


def configure_parser(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "precompute-sector-theme-state",
        help="Enrich Dashboard sector snapshots with theme-state metrics",
    )
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--config", default="~/.dojo/agents.yaml")
    parser.add_argument("--debug", action="store_true", help="Log redacted startup configuration and precompute diagnostics")
    parser.add_argument("--input-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--upload", action="store_true")
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


async def run_precompute_sector_theme_state(args: argparse.Namespace) -> int:
    data_root_str = args.data_root or FinancialDashboardConfig.dashboard_data_root
    data_root = Path(data_root_str).expanduser().resolve()
    input_dir = Path(getattr(args, "input_dir", None) or (data_root / PRECOMPUTE_DIR)).expanduser().resolve()
    output_dir = Path(getattr(args, "output_dir", None) or (data_root / PRECOMPUTE_DIR)).expanduser().resolve()
    floors = apply_configured_ticker_market_cap_mins(getattr(args, "config", None))

    LOGGER.info(
        "Enriching unified sector precompute (theme + horizon + sector/ticker alpha) -> %s",
        data_root / PRECOMPUTE_DIR,
    )
    LOGGER.info("Ticker market-cap floors: %s", floors)

    progress = _PrecomputeProgressReporter()
    on_progress: ProgressCallback = progress.callback

    config_store = ConfigStore(getattr(args, "config", None) or "~/.dojo/agents.yaml")
    agents_config = config_store.snapshot()
    log_precompute_startup(args, config_store)
    client = create_async_dojo(agents_config, online=True)
    write_client = None
    try:
        write_client = create_async_dojo(agents_config, online=True) if args.upload else None
        log_precompute_sdk_runtime(client, role="reader")
        if write_client is not None:
            log_precompute_sdk_runtime(write_client, role="writer")
        registry = FinancialDomainRegistry()
        # Phase B reads Phase A from disk; preloading old snapshots can replace it.
        await registry.init_and_load_all(client, data_root=data_root, preload=False)
        base_stores = ["sector_store", "benchmark_store"]
        if not args.skip_volume_enrich:
            base_stores.extend(["stock_store", "stock_sector_store", "kline_store"])
        await registry.ensure_stores_loaded(*base_stores)

        manifest = await build_theme_state_precomputed(
            data_root=data_root,
            source_dir=input_dir,
            out_dir=output_dir,
            sector_store=registry.sector_store,
            kline_store=None if args.skip_volume_enrich else registry.kline_store,
            benchmark_store=registry.benchmark_store,
            fin_store=None if args.skip_fundamentals else registry.stock_fin_indicators_store,
            start_date=args.start_date,
            end_date=args.end_date,
            upload_client=write_client if args.upload else None,
            skip_fundamentals=bool(args.skip_fundamentals),
            skip_volume_enrich=bool(args.skip_volume_enrich),
            on_progress=on_progress,
        )
        published_dir = Path(manifest["published_dir"])
        if registry.sector_precomputed_store is not None:
            registry.sector_precomputed_store.reload(published_dir)
        if registry.theme_state_precomputed_store is not None:
            registry.theme_state_precomputed_store.reload(published_dir)
        LOGGER.info("%s", json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    finally:
        progress.close()
        await close_async_dojo(client)
        if write_client is not None:
            await close_async_dojo(write_client)
