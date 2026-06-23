from __future__ import annotations
import argparse
import json
from pathlib import Path

from dojo.client.async_client import AsyncDojo

from dojoagents.config.models import FinancialDashboardConfig
from dojoagents.dashboard.services.financial_registry import FinancialDomainRegistry
from dojoagents.dashboard.services.precompute_sector_daily import build_sector_precomputed


async def run_precompute_sector(args: argparse.Namespace) -> int:
    data_root_str = args.data_root or FinancialDashboardConfig.dashboard_data_root
    data_root = Path(data_root_str).expanduser().resolve()

    print(f"Precomputing sector data -> {data_root / 'dojo_sector_precomputed'}")
    print(f"Window start: {args.start_date}")

    client = AsyncDojo()
    registry = FinancialDomainRegistry()
    await registry.init_and_load_all(client, data_root=data_root, preload=True)

    manifest = await build_sector_precomputed(
        data_root=data_root,
        sector_store=registry.sector_store,
        stock_sector_store=registry.stock_sector_store,
        stock_store=registry.stock_store,
        kline_store=registry.kline_store,
        start_date=args.start_date,
        upload_client=client if args.upload else None,
    )
    if registry.sector_precomputed_store is not None:
        registry.sector_precomputed_store.reload(Path(manifest["published_dir"]))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0
