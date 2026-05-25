from __future__ import annotations

from dojoagents.dojo_extensions.base import DashboardCardSpec, ExtensionHealth
from dojoagents.quant.context import QuantContext
from dojoagents.tools.registry import ToolSpec


class DojoMarketDataExtension:
    name = "dojo_market_data"
    version = "0.1"

    def health(self) -> ExtensionHealth:
        return ExtensionHealth(ok=True)

    def tool_specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="dojo.market.snapshot",
                description="Return latest normalized market snapshot for symbols.",
                parameters={
                    "type": "object",
                    "properties": {
                        "symbols": {"type": "array", "items": {"type": "string"}},
                        "market": {"type": "string", "enum": ["stock", "crypto"]},
                    },
                    "required": ["symbols", "market"],
                },
                handler=self.snapshot,
            )
        ]

    async def snapshot(self, args: dict) -> dict:
        symbols = ", ".join(args.get("symbols", []))
        market = args.get("market", "unknown")
        return {
            "content": (
                f"Dojo market snapshot facade for {market}: {symbols}. "
                "Concrete indicators are intentionally not implemented."
            )
        }

    def dashboard_cards(self) -> list[DashboardCardSpec]:
        return [DashboardCardSpec(id="market-data", title="Market Data")]

    def prompt_context(self, quant_context: QuantContext) -> str:
        symbols = ", ".join(quant_context.symbols)
        return (
            "Dojo market data extension available. "
            f"Current request targets {quant_context.market}: {symbols} "
            f"at {quant_context.timeframe}."
        )
