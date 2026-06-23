#!/usr/bin/env python3
"""Precompute sector constituents and daily index levels into AlphaDojo/data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dojoagents.dashboard.config.settings import FinancialDashboardConfig
from dojoagents.dashboard.services.precompute_sector_daily import build_sector_precomputed, DATA_START_DATE
from dojoagents.dashboard.config.store_registry import registry


def main() -> int:
    parser = argparse.ArgumentParser(description="Precompute sector daily metrics and returns")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Defaults to DojoAgents dashboard_data_root",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=DATA_START_DATE,
        help=f"First trade date to include (default {DATA_START_DATE})",
    )
    args = parser.parse_args()
    data_root = (args.data_root or FinancialDashboardConfig.dashboard_data_root).resolve()

    print(f"Precomputing sector data -> {data_root / 'dojo_sector_precomputed'}")
    print(f"Window start: {args.start_date}")
    manifest = build_sector_precomputed(
        data_root=data_root, sector_store=registry.stock_sector_store, stock_store=registry.stock_store, kline_store=registry.kline_store, start_date=args.start_date
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
