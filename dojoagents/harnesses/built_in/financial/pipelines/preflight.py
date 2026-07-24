from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .trading_calendar import (
    DEFAULT_MARKETS,
    canonical_market,
    open_markets_on,
)
from dojoagents.tasks.models import PipelineSpec


@dataclass(frozen=True)
class PipelinePreflightResult:
    action: Literal["run", "skip"]
    open_markets: tuple[str, ...]
    closed_markets: tuple[str, ...]
    reason: str


def _normalize_markets(raw: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if not raw:
        return DEFAULT_MARKETS
    markets: list[str] = []
    seen: set[str] = set()
    for item in raw:
        code = canonical_market(str(item))
        if code in seen:
            continue
        seen.add(code)
        markets.append(code)
    return tuple(markets)


def evaluate_pipeline_preflight(
    pipeline: PipelineSpec,
    *,
    trading_date: str,
    force: bool = False,
) -> PipelinePreflightResult:
    """Return run/skip for pipeline-level preflight gates.

    Skip is a successful no-op (CLI should exit 0). ``force`` bypasses gates.
    """
    if force:
        return PipelinePreflightResult(
            action="run",
            open_markets=(),
            closed_markets=(),
            reason="preflight bypassed by --force",
        )

    preflight = pipeline.preflight or {}
    required_markets = preflight.get("require_any_trading_market")
    if not required_markets:
        return PipelinePreflightResult(
            action="run",
            open_markets=(),
            closed_markets=(),
            reason="no preflight gates configured",
        )

    markets = _normalize_markets(required_markets)
    open_markets = tuple(open_markets_on(trading_date, markets))
    closed = tuple(code for code in markets if code not in set(open_markets))
    if open_markets:
        return PipelinePreflightResult(
            action="run",
            open_markets=open_markets,
            closed_markets=closed,
            reason=f"open markets on {trading_date}: {', '.join(open_markets)}",
        )
    return PipelinePreflightResult(
        action="skip",
        open_markets=(),
        closed_markets=closed,
        reason=(f"no open markets among {', '.join(markets)} on {trading_date}; " f"skipping pipeline {pipeline.id}"),
    )
