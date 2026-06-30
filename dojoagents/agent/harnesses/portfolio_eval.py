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


def parse_eval_submission(data: Any) -> PortfolioEvalSubmission | None:
    if not isinstance(data, dict):
        return None
    portfolio_id = str(data.get("portfolio_id") or "").strip()
    if not portfolio_id:
        return None

    min_by_market_raw = data.get("min_candidates_by_market")
    min_by_market: dict[str, int] | None = None
    if isinstance(min_by_market_raw, dict):
        parsed: dict[str, int] = {}
        for key, value in min_by_market_raw.items():
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
        min_by_market = parsed or None

    min_candidate_count: int | None = None
    if data.get("min_candidate_count") is not None:
        try:
            parsed_count = int(data["min_candidate_count"])
            if parsed_count > 0:
                min_candidate_count = parsed_count
        except (TypeError, ValueError):
            min_candidate_count = None

    return PortfolioEvalSubmission(
        portfolio_id=portfolio_id,
        task_summary=str(data.get("task_summary") or "").strip(),
        require_kind_agent=bool(data.get("require_kind_agent", False)),
        min_candidate_count=min_candidate_count,
        min_candidates_by_market=min_by_market,
    )


def candidate_count_from_detail(data: object) -> int:
    if not isinstance(data, dict):
        return 0
    candidates = data.get("candidates")
    if isinstance(candidates, list):
        return len(candidates)
    holdings = data.get("holdings")
    if isinstance(holdings, list):
        return len(holdings)
    return 0


def candidates_by_market_from_detail(data: object) -> dict[str, int]:
    counts = {"us": 0, "cn": 0, "hk": 0}
    if not isinstance(data, dict):
        return counts
    rows = data.get("candidates")
    if not isinstance(rows, list):
        rows = data.get("holdings")
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


def eval_summary_from_detail(data: object) -> dict[str, Any]:
    """Compact counts for portfolio_eval_submit — always from portfolio_read_detail."""
    total = candidate_count_from_detail(data)
    by_market = candidates_by_market_from_detail(data)
    return {
        "candidate_count": total,
        "candidate_count_by_market": by_market,
        "guidance": (
            "Set min_candidate_count / min_candidates_by_market from these ACTUAL counts only. "
            "Do not use pre-add filter estimates. Omit per-market minimums unless the user explicitly asked."
        ),
    }


def verify_eval_submission(
    submission: PortfolioEvalSubmission,
    detail_data: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    detail_id = str(detail_data.get("id") or "")
    if detail_id != submission.portfolio_id:
        issues.append(
            f"Eval portfolio_id {submission.portfolio_id} does not match portfolio_read_detail id {detail_id}."
        )

    if submission.require_kind_agent and str(detail_data.get("kind") or "") != "agent":
        issues.append("Eval requires kind=agent (DojoAgent-generated) but portfolio is not agent-owned.")

    actual_count = candidate_count_from_detail(detail_data)
    if submission.min_candidate_count is not None and actual_count < submission.min_candidate_count:
        issues.append(
            f"Portfolio has {actual_count} candidate(s) but eval requires at least {submission.min_candidate_count}."
        )

    if submission.min_candidates_by_market:
        by_market = candidates_by_market_from_detail(detail_data)
        for market, required in submission.min_candidates_by_market.items():
            actual = by_market.get(market, 0)
            if actual < required:
                issues.append(
                    f"Market {market.upper()} has {actual} candidate(s) but eval requires at least {required}."
                )

    return issues
