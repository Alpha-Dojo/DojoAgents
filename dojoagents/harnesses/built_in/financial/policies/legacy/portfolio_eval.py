from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PortfolioEvalSubmission:
    """Agent-declared success criteria for a portfolio task (no keyword parsing)."""

    portfolio_id: str
    task_summary: str = ""
    require_kind_agent: bool = False
    min_candidate_count: int | None = None
    min_candidates_by_market: dict[str, int] | None = None
    min_position_count: int | None = None
    min_positions_by_market: dict[str, int] | None = None
    max_position_count: int | None = None


def parse_eval_submission(data: Any) -> PortfolioEvalSubmission | None:
    if not isinstance(data, dict):
        return None
    portfolio_id = str(data.get("portfolio_id") or "").strip()
    if not portfolio_id:
        return None

    def _parse_market_minimums(raw: object) -> dict[str, int] | None:
        if not isinstance(raw, dict):
            return None
        parsed: dict[str, int] = {}
        for key, value in raw.items():
            market = str(key).strip().lower()
            if market == "sh":
                market = "cn"
            if market not in {"us", "cn", "hk"}:
                continue
            try:
                count = int(value)
            except (TypeError, ValueError):
                continue
            if count > 0:
                parsed[market] = count
        return parsed or None

    min_by_market = _parse_market_minimums(data.get("min_candidates_by_market"))
    min_positions_by_market = _parse_market_minimums(data.get("min_positions_by_market"))

    min_candidate_count: int | None = None
    if data.get("min_candidate_count") is not None:
        try:
            parsed_count = int(data["min_candidate_count"])
            if parsed_count > 0:
                min_candidate_count = parsed_count
        except (TypeError, ValueError):
            min_candidate_count = None

    min_position_count: int | None = None
    if data.get("min_position_count") is not None:
        try:
            parsed_count = int(data["min_position_count"])
            if parsed_count > 0:
                min_position_count = parsed_count
        except (TypeError, ValueError):
            min_position_count = None

    max_position_count: int | None = None
    if data.get("max_position_count") is not None:
        try:
            parsed_max = int(data["max_position_count"])
            if parsed_max >= 0:
                max_position_count = parsed_max
        except (TypeError, ValueError):
            max_position_count = None

    return PortfolioEvalSubmission(
        portfolio_id=portfolio_id,
        task_summary=str(data.get("task_summary") or "").strip(),
        require_kind_agent=bool(data.get("require_kind_agent", False)),
        min_candidate_count=min_candidate_count,
        min_candidates_by_market=min_by_market,
        min_position_count=min_position_count,
        min_positions_by_market=min_positions_by_market,
        max_position_count=max_position_count,
    )


def candidate_count_from_detail(data: object) -> int:
    if not isinstance(data, dict):
        return 0
    candidates = data.get("candidates")
    if isinstance(candidates, list):
        return len(candidates)
    return 0


def candidates_by_market_from_detail(data: object) -> dict[str, int]:
    counts = {"us": 0, "cn": 0, "hk": 0}
    if not isinstance(data, dict):
        return counts
    rows = data.get("candidates")
    if not isinstance(rows, list):
        return counts
    for row in rows:
        if not isinstance(row, dict):
            continue
        market = str(row.get("market") or "").strip().lower()
        if market in {"sh", "cn"}:
            counts["cn"] += 1
        elif market in counts:
            counts[market] += 1
    return counts


def _position_rows_from_detail(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("positions", "holdings"):
        rows = data.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def position_count_from_detail(data: object) -> int:
    if not isinstance(data, dict):
        return 0
    return sum(1 for row in _position_rows_from_detail(data) if float(row.get("shares") or 0) > 0)


def positions_by_market_from_detail(data: object) -> dict[str, int]:
    counts = {"us": 0, "cn": 0, "hk": 0}
    if not isinstance(data, dict):
        return counts
    for row in _position_rows_from_detail(data):
        if float(row.get("shares") or 0) <= 0:
            continue
        market = str(row.get("market") or "").strip().lower()
        if market in {"sh", "cn"}:
            counts["cn"] += 1
        elif market in counts:
            counts[market] += 1
    return counts


def eval_summary_from_detail(data: object) -> dict[str, Any]:
    """Compact counts for portfolio_eval_submit — always from portfolio_read_detail."""
    total_candidates = candidate_count_from_detail(data)
    candidates_by_market = candidates_by_market_from_detail(data)
    total_positions = position_count_from_detail(data)
    positions_by_market = positions_by_market_from_detail(data)
    return {
        "candidate_count": total_candidates,
        "candidate_count_by_market": candidates_by_market,
        "position_count": total_positions,
        "position_count_by_market": positions_by_market,
        "guidance": (
            "CANDIDATES (候选股/watchlist): use portfolio_write_add_candidate(s). "
            "Set min_candidate_count only for watchlist tasks. "
            "POSITIONS (持仓/建仓/buy at cost): use portfolio_write_create_order(s). "
            "POSITION SYNC (仓位同步/外部导入): use portfolio_write_sync_positions — NOT create_order. "
            "Set min_position_count for 建仓 tasks. "
            "Set max_position_count=0 for 清仓/liquidation tasks. "
            "Use ACTUAL counts from this summary — never pre-add estimates."
        ),
    }


def verify_eval_submission(
    submission: PortfolioEvalSubmission,
    detail_data: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    detail_id = str(detail_data.get("id") or "")
    if detail_id != submission.portfolio_id:
        issues.append(f"Eval portfolio_id {submission.portfolio_id} does not match portfolio_read_detail id {detail_id}.")

    if submission.require_kind_agent and str(detail_data.get("kind") or "") != "agent":
        issues.append("Eval requires kind=agent (DojoAgent-generated) but portfolio is not agent-owned.")

    actual_count = candidate_count_from_detail(detail_data)
    if submission.min_candidate_count is not None and actual_count < submission.min_candidate_count:
        issues.append(f"Portfolio has {actual_count} candidate(s) but eval requires at least {submission.min_candidate_count}.")

    if submission.min_candidates_by_market:
        by_market = candidates_by_market_from_detail(detail_data)
        for market, required in submission.min_candidates_by_market.items():
            actual = by_market.get(market, 0)
            if actual < required:
                issues.append(f"Market {market.upper()} has {actual} candidate(s) but eval requires at least {required}.")

    actual_positions = position_count_from_detail(detail_data)
    if submission.min_position_count is not None and actual_positions < submission.min_position_count:
        issues.append(
            f"Portfolio has {actual_positions} filled position(s) but eval requires at least "
            f"{submission.min_position_count}. Use portfolio_write_create_order(s), not add_candidate."
        )

    if submission.min_positions_by_market:
        by_market = positions_by_market_from_detail(detail_data)
        for market, required in submission.min_positions_by_market.items():
            actual = by_market.get(market, 0)
            if actual < required:
                issues.append(f"Market {market.upper()} has {actual} filled position(s) but eval requires at least {required}.")

    if submission.max_position_count is not None and actual_positions > submission.max_position_count:
        issues.append(f"Portfolio has {actual_positions} filled position(s) but eval requires at most " f"{submission.max_position_count} (清仓/liquidation not complete).")

    return issues
