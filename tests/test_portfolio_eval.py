from __future__ import annotations

from dojoagents.harnesses.built_in.financial.policies.legacy.portfolio_eval import (
    PortfolioEvalSubmission,
    eval_summary_from_detail,
    parse_eval_submission,
    verify_eval_submission,
)


def test_parse_eval_submission_accepts_market_minimums() -> None:
    parsed = parse_eval_submission(
        {
            "portfolio_id": "p-1",
            "task_summary": "Three-market basket",
            "min_candidates_by_market": {"us": 2, "cn": 1, "hk": 1},
        }
    )
    assert parsed is not None
    assert parsed.min_candidates_by_market == {"us": 2, "cn": 1, "hk": 1}


def test_verify_eval_submission_checks_per_market_counts() -> None:
    submission = PortfolioEvalSubmission(
        portfolio_id="p-1",
        min_candidates_by_market={"us": 2, "cn": 1, "hk": 1},
    )
    detail = {
        "id": "p-1",
        "candidates": [
            {"ticker": "AAPL", "market": "us"},
            {"ticker": "600519", "market": "cn"},
        ],
    }
    issues = verify_eval_submission(submission, detail)
    assert any("US" in issue for issue in issues)
    assert any("HK" in issue for issue in issues)


def test_eval_summary_from_detail() -> None:
    detail = {
        "id": "p-1",
        "candidates": [
            {"ticker": "AAPL", "market": "us"},
            {"ticker": "600519", "market": "sh"},
            {"ticker": "0700", "market": "hk"},
        ],
        "positions": [
            {"ticker": "NVDA", "market": "us", "shares": 10},
        ],
    }
    summary = eval_summary_from_detail(detail)
    assert summary["candidate_count"] == 3
    assert summary["candidate_count_by_market"] == {"us": 1, "cn": 1, "hk": 1}
    assert summary["position_count"] == 1
    assert summary["position_count_by_market"] == {"us": 1, "cn": 0, "hk": 0}


def test_verify_eval_submission_checks_position_counts() -> None:
    submission = PortfolioEvalSubmission(
        portfolio_id="p-1",
        min_position_count=2,
    )
    detail = {
        "id": "p-1",
        "candidates": [{"ticker": "AAPL", "market": "us"}],
        "positions": [{"ticker": "AAPL", "market": "us", "shares": 5}],
    }
    issues = verify_eval_submission(submission, detail)
    assert any("filled position" in issue for issue in issues)
