from __future__ import annotations

import pytest

from dojoagents.harnesses.built_in.financial.services.sector_leader_concentration import (
    compute_leader_concentration,
    leader_concentration_tier,
)


def test_leader_concentration_user_example() -> None:
    # Leader +46% @ 15% weight → +6.9 pts; others drag; sector ≈ +6.5 → ~106%.
    members = [
        ("LEAD", 15.0, 46.0),
        ("A", 85.0 / 8, -0.5),
        ("B", 85.0 / 8, -0.5),
        ("C", 85.0 / 8, -0.5),
        ("D", 85.0 / 8, -0.5),
        ("E", 85.0 / 8, -0.5),
        ("F", 85.0 / 8, -0.5),
        ("G", 85.0 / 8, -0.5),
        ("H", 85.0 / 8, -0.5),
    ]
    sector_ret = sum((cap / 100.0) * ret for _, cap, ret in members)
    assert sector_ret == pytest.approx(6.475, abs=1e-6)

    result = compute_leader_concentration(members, sector_ret)
    assert result is not None
    assert result.leader_ticker == "LEAD"
    assert result.leader_weight_pct == pytest.approx(15.0)
    assert result.leader_contribution_pct == pytest.approx(6.9)
    assert result.leader_concentration_pct == pytest.approx(6.9 / sector_ret * 100.0)
    assert result.leader_concentration_tier == "extreme"


def test_leader_concentration_tiers() -> None:
    assert leader_concentration_tier(81.0) == "extreme"
    assert leader_concentration_tier(80.0) == "moderate"
    assert leader_concentration_tier(50.0) == "moderate"
    assert leader_concentration_tier(49.9) == "healthy"
    assert leader_concentration_tier(-90.0) == "extreme"


def test_leader_concentration_requires_sector_move() -> None:
    assert compute_leader_concentration([("A", 100.0, 1.0)], 0.0) is None
    assert compute_leader_concentration([], 5.0) is None
