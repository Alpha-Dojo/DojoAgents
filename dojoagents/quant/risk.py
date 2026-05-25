from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RiskSnapshot:
    summary: str
    metrics: dict[str, Any] = field(default_factory=dict)
