"""CLI adapter contributed by the built-in Financial Harness."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..context import FinancialContext


class FinancialCliSurface:
    def __init__(self, service_container):
        self.service_container = service_container

    @property
    def services(self):
        return self.service_container

    def configure_parser(
        self,
        subcommands: argparse._SubParsersAction,
        chat_parser: argparse.ArgumentParser,
    ) -> None:
        chat_parser.add_argument("--market", choices=["stock", "crypto"])
        chat_parser.add_argument("--symbols", default="")
        chat_parser.add_argument("--timeframe", default="1d")

        precompute = subcommands.add_parser(
            "precompute-sector",
            help="Precompute sector daily metrics and returns",
        )
        precompute.add_argument("--data-root", type=Path, default=None)
        precompute.add_argument("--start-date", default="2025-01-01")
        precompute.add_argument("--upload", action="store_true")
        precompute.add_argument("--with-theme-state", action="store_true")
        precompute.add_argument("--skip-fundamentals", action="store_true")
        precompute.add_argument("--skip-volume-enrich", action="store_true")

        theme_state = subcommands.add_parser(
            "precompute-sector-theme-state",
            help="Enrich sector snapshots with theme-state metrics",
        )
        theme_state.add_argument("--data-root", type=Path, default=None)
        theme_state.add_argument("--input-dir", type=Path, default=None)
        theme_state.add_argument("--output-dir", type=Path, default=None)
        theme_state.add_argument("--start-date", default=None)
        theme_state.add_argument("--end-date", default=None)
        theme_state.add_argument("--upload", action="store_true")
        theme_state.add_argument("--skip-fundamentals", action="store_true")
        theme_state.add_argument("--skip-volume-enrich", action="store_true")

        from .cli_tasks import add_tasks_parser

        add_tasks_parser(subcommands)

    def request_context_from_args(self, args: argparse.Namespace):
        if not getattr(args, "market", None) or not getattr(
            args,
            "symbols",
            "",
        ):
            return None
        return FinancialContext(
            market=args.market,
            symbols=tuple(symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()),
            timeframe=args.timeframe,
        )

    async def run_command(self, args: argparse.Namespace) -> int | None:
        if args.command == "precompute-sector":
            from ..pipelines.cli_precompute_sector import run_precompute_sector

            return await run_precompute_sector(args)
        if args.command == "precompute-sector-theme-state":
            from ..pipelines.cli_precompute_sector_theme_state import (
                run_precompute_sector_theme_state,
            )

            return await run_precompute_sector_theme_state(args)
        if args.command == "tasks":
            from .cli_tasks import run_tasks_command

            return await run_tasks_command(args)
        return None


__all__ = ["FinancialCliSurface"]
