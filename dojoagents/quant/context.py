from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class QuantContext:
    market: Literal["stock", "crypto"]
    symbols: list[str]
    timeframe: str
    currency: str = "USD"
    data_freshness: str = "latest_available"

    def prompt_block(self) -> str:
        symbols = ", ".join(self.symbols)
        return (
            "Quant context:\n"
            f"- market: {self.market}\n"
            f"- symbols: {symbols}\n"
            f"- timeframe: {self.timeframe}\n"
            f"- currency: {self.currency}\n"
            f"- data freshness: {self.data_freshness}"
        )
