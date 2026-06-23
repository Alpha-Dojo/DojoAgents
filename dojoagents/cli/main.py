from __future__ import annotations
from dojoagents.logging import LOGGER

import argparse
import asyncio
from pathlib import Path

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
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
