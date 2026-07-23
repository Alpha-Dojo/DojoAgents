"""Portfolio request intent helpers owned by the Dashboard application."""

from __future__ import annotations

import re

_LIQUIDATE_RE = re.compile(
    r"(?:全部清仓|清仓|全部卖出|全部卖掉|清掉|清空持仓|清掉持仓|" r"liquidate\s+all|close\s+all\s+(?:holdings|positions)|" r"sell\s+all\s+(?:holdings|positions))",
    re.IGNORECASE,
)


def is_liquidation_intent(message: str) -> bool:
    return bool(_LIQUIDATE_RE.search((message or "").strip()))


__all__ = ["is_liquidation_intent"]
