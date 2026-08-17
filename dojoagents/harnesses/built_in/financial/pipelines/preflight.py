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
    market: str | None = None,
    force: bool = False,
) -> PipelinePreflightResult:
    """Return run/skip for pipeline-level preflight gates.

    Skip is a successful no-op (CLI should exit 0). ``force`` bypasses gates.

    When ``preflight.require_market`` is true, ``market`` must be provided and
    that market must be open on ``trading_date`` (unless ``force``).
    Legacy ``require_any_trading_market`` still means: run if any listed market is open.
    """
    if force:
        return PipelinePreflightResult(
            action="run",
            open_markets=(),
            closed_markets=(),
            reason="preflight bypassed by --force",
        )

    preflight = pipeline.preflight or {}
    require_market = bool(preflight.get("require_market"))
    allowed_raw = preflight.get("allowed_markets")
    any_markets = preflight.get("require_any_trading_market")

    if require_market:
        if not str(market or "").strip():
            raise ValueError(f"market is required for pipeline {pipeline.id}")
        code = canonical_market(str(market))
        allowed = _normalize_markets(allowed_raw) if allowed_raw else DEFAULT_MARKETS
        if code not in set(allowed):
            raise ValueError(
                f"Unsupported market {code!r} for pipeline {pipeline.id}; "
                f"allowed: {', '.join(allowed)}"
            )
        open_markets = tuple(open_markets_on(trading_date, (code,)))
        if open_markets:
            return PipelinePreflightResult(
                action="run",
                open_markets=open_markets,
                closed_markets=(),
                reason=f"market {code} open on {trading_date}",
            )
        return PipelinePreflightResult(
            action="skip",
            open_markets=(),
            closed_markets=(code,),
            reason=(
                f"market {code} closed on {trading_date}; "
                f"skipping pipeline {pipeline.id}"
            ),
        )

    if not any_markets:
        return PipelinePreflightResult(
            action="run",
            open_markets=(),
            closed_markets=(),
            reason="no preflight gates configured",
        )

    markets = _normalize_markets(any_markets)
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
        reason=(
            f"no open markets among {', '.join(markets)} on {trading_date}; "
            f"skipping pipeline {pipeline.id}"
        ),
    )


__all__ = ["PipelinePreflightResult", "evaluate_pipeline_preflight"]
