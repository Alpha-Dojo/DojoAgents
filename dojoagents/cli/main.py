from __future__ import annotations

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

    gateway = sub.add_parser("gateway")
    gateway_sub = gateway.add_subparsers(dest="gateway_command")
    gateway_setup = gateway_sub.add_parser("setup")
    gateway_setup.add_argument("adapter", help="Adapter name or 'all'")
    gateway_setup.add_argument("--config", default="~/.dojo/agents.yaml")
    gateway.add_argument("--host", default="127.0.0.1")
    gateway.add_argument("--port", type=int, default=8766)
    gateway.add_argument("--config", default="~/.dojo/agents.yaml")

    sub.add_parser("scheduler")
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
    print(response.content)
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
        uvicorn.run(create_gateway_app(config_path=args.config), host=args.host, port=args.port)
        return 0
    if args.command == "scheduler":
        runtime = Runtime.from_default_config()
        print(f"Loaded {len(runtime.scheduler.list_jobs())} scheduled jobs")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
