from __future__ import annotations

import pytest

from dojoagents.dashboard.services.sector_movers_ranking import (
    DEFAULT_SECTOR_MOVERS_MIN_TOTAL_MARKET_CAP,
    MIN_SECTOR_MEMBER_COUNT_FOR_MOVERS_RANKING,
    sector_eligible_for_movers_ranking,
)


def test_default_sector_movers_min_total_cap_matches_ui_200yi() -> None:
    assert DEFAULT_SECTOR_MOVERS_MIN_TOTAL_MARKET_CAP == 200 * 1e8


def test_sector_eligible_requires_multi_member_basket() -> None:
    assert MIN_SECTOR_MEMBER_COUNT_FOR_MOVERS_RANKING == 5
    assert sector_eligible_for_movers_ranking(member_count=4) is False
    assert sector_eligible_for_movers_ranking(member_count=5) is True


def test_sector_eligible_respects_total_market_cap_floor() -> None:
    assert sector_eligible_for_movers_ranking(
        member_count=5,
        total_market_cap=50.0,
        min_total_market_cap=100.0,
    ) is False
    assert sector_eligible_for_movers_ranking(
        member_count=5,
        total_market_cap=150.0,
        min_total_market_cap=100.0,
    ) is True


@pytest.mark.parametrize(
    ("member_count", "expected"),
    [
        (0, False),
        (1, False),
        (2, False),
        (4, False),
        (5, True),
        (10, True),
    ],
)
def test_sector_eligible_member_count_matrix(member_count: int, expected: bool) -> None:
    assert sector_eligible_for_movers_ranking(member_count=member_count) is expected
