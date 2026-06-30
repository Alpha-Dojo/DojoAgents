from __future__ import annotations

import pytest

from dojoagents.dashboard.tools import portfolio_tools


def test_assert_candidate_only_fields_rejects_price() -> None:
    with pytest.raises(RuntimeError, match="portfolio_write_create_order"):
        portfolio_tools._assert_candidate_only_fields(
            {"ticker": "NVDA", "price": 100.0, "qty": 10},
            context="portfolio_write_add_candidates",
        )


def test_assert_candidate_only_fields_allows_ticker_only() -> None:
    portfolio_tools._assert_candidate_only_fields(
        {"ticker": "NVDA", "market": "us"},
        context="portfolio_write_add_candidates",
    )
