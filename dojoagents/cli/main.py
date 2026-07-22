from __future__ import annotations

from pathlib import Path
from dojoagents.logging import LOGGER

import argparse
import asyncio

import uvicorn

from dojoagents.agent.models import ChatRequest
from dojoagents.agent.runtime import Runtime
from dojoagents.cli.gateway_setup import configure_gateway_adapters
from dojoagents.dashboard.server import create_app as create_dashboard_app
from dojoagents.gateway.server import create_runner_app as create_gateway_app
from dojoagents.quant.context import QuantContext


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dojoagents")
    sub = parser.add_subparsers(dest="command", required=True)

    chat = sub.add_parser("chat")
    chat.add_argument("message", nargs="?", default="")
    chat.add_argument("--profile", default="default")
    chat.add_argument("--market", choices=["stock", "crypto"])
    chat.add_argument("--symbols", default="")
    chat.add_argument("--timeframe", default="1d")

    dashboard = sub.add_parser("dashboard")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8765)

    sessions = sub.add_parser("sessions")
    sessions_sub = sessions.add_subparsers(dest="sessions_command", required=True)
    sessions_export = sessions_sub.add_parser("export", help="Export stored session messages")
    sessions_export.add_argument("--config", default="~/.dojo/agents.yaml")
    sessions_export.add_argument("--session-id", default=None, help="Export only one session")
    sessions_export.add_argument("--output-dir", default=None)
    sessions_export.add_argument("--format", default="jsonl")
    sessions_export.add_argument("--include-archived", action="store_true")
    sessions_export.add_argument("--no-raw-strands", action="store_true")
    sessions_export.add_argument("--no-dojo-sidecars", action="store_true")
    sessions_export.add_argument("--no-memory", action="store_true")
    sessions_export.add_argument("--no-token-usage", action="store_true")

    gateway = sub.add_parser("gateway")
    gateway_sub = gateway.add_subparsers(dest="gateway_command")
    gateway_setup = gateway_sub.add_parser("setup")
    gateway_setup.add_argument("adapter", help="Adapter name or 'all'")
    gateway_setup.add_argument("--config", default="~/.dojo/agents.yaml")

    gateway_pairing = gateway_sub.add_parser("pairing")
    pairing_sub = gateway_pairing.add_subparsers(dest="pairing_command", required=True)

    pairing_list = pairing_sub.add_parser("list")
    pairing_list.add_argument("--platform", default=None)
    pairing_list.add_argument("--config", default="~/.dojo/agents.yaml")

    pairing_approve = pairing_sub.add_parser("approve")
    pairing_approve.add_argument("platform")
    pairing_approve.add_argument("code")
    pairing_approve.add_argument("--config", default="~/.dojo/agents.yaml")

    pairing_deny = pairing_sub.add_parser("deny")
    pairing_deny.add_argument("platform")
    pairing_deny.add_argument("code")
    pairing_deny.add_argument("--config", default="~/.dojo/agents.yaml")

    gateway.add_argument("--host", default="127.0.0.1")
    gateway.add_argument("--port", type=int, default=8766)
    gateway.add_argument("--config", default="~/.dojo/agents.yaml")

    sub.add_parser("scheduler")

    model_parser = sub.add_parser("model")
    model_parser.add_argument("--config", default="~/.dojo/agents.yaml")

    mcp_parser = sub.add_parser("mcp")
    mcp_sub = mcp_parser.add_subparsers(dest="mcp_command", required=True)
    _ = mcp_sub.add_parser("serve")

    precompute = sub.add_parser("precompute-sector", help="Precompute sector daily metrics and returns")
    precompute.add_argument("--data-root", type=Path, default=None, help="Defaults to DojoAgents dashboard_data_root")
    precompute.add_argument("--start-date", default="2025-01-01", help="First trade date to include (default 2025-01-01)")
    precompute.add_argument("--upload", action="store_true", help="Upload published snapshot to dojo_sector_precomputed")
    precompute.add_argument(
        "--with-theme-state",
        action="store_true",
        help="After Phase A, enrich with theme-state, horizon, and sector/ticker alpha factors",
    )
    precompute.add_argument(
        "--skip-fundamentals",
        action="store_true",
        help="When used with --with-theme-state, skip fundamentals_lite fetch",
    )
    precompute.add_argument(
        "--skip-volume-enrich",
        action="store_true",
        help="When used with --with-theme-state, skip kline volume enrichment",
    )

    theme_state = sub.add_parser(
        "precompute-sector-theme-state",
        help=(
            "Enrich dojo_sector_precomputed with theme-state, horizon metrics, "
            "sector_alpha_factors_daily, and ticker_alpha_factors_daily (short + mid)"
        ),
    )
    theme_state.add_argument("--data-root", type=Path, default=None, help="Defaults to DojoAgents dashboard_data_root")
    theme_state.add_argument("--start-date", default=None, help="Optional first trade date to include")
    theme_state.add_argument("--end-date", default=None, help="Optional last trade date to include")
    theme_state.add_argument(
        "--upload",
        action="store_true",
        help="Upload unified snapshot to dojo_sector_precomputed",
    )
    theme_state.add_argument("--skip-fundamentals", action="store_true", help="Skip fundamentals_lite aggregation")
    theme_state.add_argument("--skip-volume-enrich", action="store_true", help="Skip kline volume enrichment for breadth")

    from dojoagents.cli.tasks import add_tasks_parser

    add_tasks_parser(sub)

    return parser


async def _run_chat(args: argparse.Namespace) -> int:
    runtime = Runtime.from_default_config()
    quant = None
    if args.market and args.symbols:
        quant = QuantContext(
            market=args.market,
            symbols=[symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()],
            timeframe=args.timeframe,
        )
    response = await runtime.agent.run(
        ChatRequest(
            user_id="local",
            session_id="cli",
            message=args.message or input("> "),
            quant=quant,
        )
    )
    LOGGER.info(response.content)
    return 0


def _run_sessions(args: argparse.Namespace) -> int:
    from dojoagents.config.loader import ConfigStore
    from dojoagents.agent.session_manager import DojoAgentSessionManager

    if args.sessions_command == "export":
        sessions_config = ConfigStore(args.config).snapshot().sessions
        manager = DojoAgentSessionManager(
            root=sessions_config.root,
            agent_id=sessions_config.agent_id,
            provider=sessions_config.provider,
            sync_memory=False,
            export_default_dir=sessions_config.export_default_dir,
            enabled=sessions_config.enabled,
        )
        result = manager.export_all_sync(
            {
                "session_id": args.session_id,
                "output_dir": args.output_dir,
                "format": args.format,
                "include_archived": args.include_archived,
                "include_raw_strands": not args.no_raw_strands,
                "include_dojo_sidecars": not args.no_dojo_sidecars,
                "include_memory": not args.no_memory,
                "include_token_usage": not args.no_token_usage,
            }
        )
        LOGGER.info("Exported %s sessions and %s messages to %s", result.session_count, result.message_count, result.export_dir)
        for file in result.files:
            LOGGER.info(" - %s", file)
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        if argv is not None:
            return int(exc.code)
        raise
    if args.command == "chat":
        return asyncio.run(_run_chat(args))
    if args.command == "dashboard":
        runtime = Runtime.from_default_config()
        uvicorn.run(create_dashboard_app(runtime), host=args.host, port=args.port)
        return 0
    if args.command == "sessions":
        return _run_sessions(args)
    if args.command == "gateway":
        if args.gateway_command == "setup":
            return configure_gateway_adapters(args.adapter, config_path=args.config)
        if args.gateway_command == "pairing":
            from dojoagents.gateway.pairing import PairingStore
            from dojoagents.config.loader import ConfigStore

            raw_config = ConfigStore(args.config).raw()
            gateway_config = raw_config.get("gateway") or {}
            pairing_store_path = gateway_config.get("pairing_store", "~/.dojo/gateway/pairing.json")
            store = PairingStore(filepath=pairing_store_path)

            if args.pairing_command == "list":
                pending = store.list_pending(platform=args.platform)
                if not pending:
                    LOGGER.info("No pending pairing requests found.")
                else:
                    LOGGER.info(f"{'Platform':<15} {'User ID':<20} {'User Name':<20} {'Pairing Code':<15}")
                    LOGGER.info("-" * 75)
                    for p in pending:
                        LOGGER.info(f"{p['platform']:<15} {p['user_id']:<20} {p['user_name']:<20} {p['code']:<15}")
                return 0

            elif args.pairing_command == "approve":
                try:
                    success = store.approve_code(args.platform, args.code)
                    if success:
                        LOGGER.info(f"Successfully approved pairing code '{args.code}' for platform '{args.platform}'.")
                        return 0
                    else:
                        LOGGER.info(f"Failed to approve pairing code '{args.code}' on platform '{args.platform}': code not found or invalid.")
                        return 1
                except Exception as e:
                    LOGGER.info(f"Error: {str(e)}")
                    return 1

            elif args.pairing_command == "deny":
                success = store.deny_code(args.platform, args.code)
                if success:
                    LOGGER.info(f"Successfully denied pairing code '{args.code}' for platform '{args.platform}'.")
                    return 0
                else:
                    LOGGER.info(f"Failed to deny pairing code '{args.code}' on platform '{args.platform}': code not found.")
                    return 1

        uvicorn.run(create_gateway_app(config_path=args.config), host=args.host, port=args.port)
        return 0
    if args.command == "scheduler":
        runtime = Runtime.from_default_config()
        LOGGER.info(f"Loaded {len(runtime.scheduler.list_jobs())} scheduled jobs")
        return 0
    if args.command == "model":
        from dojoagents.cli.model_setup import configure_model_connection

        return configure_model_connection(config_path=args.config)
    if args.command == "mcp":
        if args.mcp_command == "serve":
            from dojoagents.cli.mcp_serve import run_server

            run_server()
            return 0
    if args.command == "precompute-sector":
        from dojoagents.cli.precompute_sector import run_precompute_sector

        return asyncio.run(run_precompute_sector(args))
    if args.command == "precompute-sector-theme-state":
        from dojoagents.cli.precompute_sector_theme_state import run_precompute_sector_theme_state

        return asyncio.run(run_precompute_sector_theme_state(args))
    if args.command == "tasks":
        from dojoagents.cli.tasks import run_tasks_command

        return asyncio.run(run_tasks_command(args))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
